from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Depends, Query, HTTPException

from app.service.rbac_service import require_permission
from app.constants.rbac import Permission
from app.model.audio_admin_model import (
    AudioDocListResp,
    AudioSegmentsResp,
    AudioTranscriptResp,
    AudioStatsResp,
    UpdateVisibilityReq,
    UpdateVisibilityResp,
    BulkDeleteReq,
    BulkDeleteResp,
    BulkReindexReq,
    BulkReindexResp,
    ReindexItem,
    ResetAudioCollectionResp,
)
from app.db_ops.audio_sql import (
    get_audio_stats,
    get_audio_transcript,
    get_audio_document,
    get_audio_segment,
    delete_audio_segments,
    delete_audio_document,
    update_audio_indexed,
    list_audio_segments,
    list_audio_documents,
    update_audio_visibility,
    is_audio_running,
    update_audio_status
)
from app.service.chroma_audio_service import (
    update_visibility_by_audio_id,
    delete_many_audio_ids
)
from app.utils.visibility_validation import parse_visibility
from app.db_ops.audio_job_sql import (
    bind_task,
    create_job
)
from app.config import settings
from app.celery_app import celery_app


audio_admin_router = APIRouter(
    prefix="/audio/admin",
    tags=["音频管理路由"],
    dependencies=
    [
        Depends(require_permission(Permission.PERM_KB_MANAGE_DOCS)),
    ]
)


@audio_admin_router.get("/stats", response_model=AudioStatsResp)
def get_stats():
    """ 获取音频表（audio_documents）的描述信息 """
    s = get_audio_stats()
    return AudioStatsResp(**s)


@audio_admin_router.get("/docs", response_model=AudioDocListResp)
def list_docs(
    q: Optional[str] = Query(default=None),
    visibility: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    uploader_user_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """
    分页列出音频的文档信息

    :param q: 查询键
    :param visibility: 音频可见性
    :param status: 音频的状态
    :param uploader_user_id: 上传者 ID
    :param page: 页数，第几页
    :param page_size: 每页容纳几条数据
    :return: AudioDocListResp
    """

    total, items = list_audio_documents(
        q=q,
        visibility=visibility,
        status=status,
        uploader_user_id=uploader_user_id,
        page=page,
        page_size=page_size,
    )
    return AudioDocListResp(total=total, page=page, page_size=page_size, items=items)


@audio_admin_router.get("/docs/{audio_id}/segments", response_model=AudioSegmentsResp)
def get_segments(
    audio_id: str,
    limit: int = Query(default=2000, ge=1, le=5000),
):
    """
    根据 audio_id 获取 limit 条分段信息

    :param audio_id: 音频 ID
    :param limit: 限制的条数
    :return: AudioSegmentsResp
    """

    doc = get_audio_document(audio_id)
    if not doc:
        raise HTTPException(status_code=404, detail="音频未找到")
    items = list_audio_segments(audio_id, limit=limit)
    return AudioSegmentsResp(audio_id=audio_id, items=items)


@audio_admin_router.get("/docs/{audio_id}/transcript", response_model=AudioTranscriptResp)
def get_transcript(
    audio_id: str,
    max_segments: int = Query(default=5000, ge=1, le=5000),
):
    """
    根据 audio_id 获取音频的转写信息

    :param audio_id: 音频 ID
    :param max_segments: 最多返回的音频分段的数量
    :return: AudioTranscriptResp
    """
    doc = get_audio_document(audio_id)
    if not doc:
        raise HTTPException(status_code=404, detail="音频未找到")
    t = get_audio_transcript(audio_id, max_segments=max_segments)
    return AudioTranscriptResp(audio_id=audio_id, transcript=t)


@audio_admin_router.patch("/docs/{audio_id}/visibility", response_model=UpdateVisibilityResp)
def set_visibility(
    audio_id: str,
    req: UpdateVisibilityReq
):
    """
    设置 audio_id 对应的音频可见性

    :param audio_id: 音频 ID
    :param req: 请求体
    :return: UpdateVisibilityResp
    """

    doc = get_audio_document(audio_id)
    if not doc:
        raise HTTPException(status_code=404, detail="音频未找到")

    v = parse_visibility(req.visibility)
    update_audio_visibility(audio_id, v)                                # MySql 中更新

    vectors = update_visibility_by_audio_id(audio_id, v)                # chroma 中更新

    return UpdateVisibilityResp(audio_id=audio_id, visibility=v, vectors_updated=int(vectors))


@audio_admin_router.post("/docs/bulk-delete", response_model=BulkDeleteResp)
def bulk_delete(req: BulkDeleteReq):
    """
    批量删除音频

    :param req: 请求体
    :return: BulkDeleteResp
    """

    audio_ids = [a.strip() for a in (req.audio_ids or []) if (a or "").strip()]
    if not audio_ids:
        raise HTTPException(status_code=400, detail="音频ID列表为空")

    vectors_deleted = delete_many_audio_ids(audio_ids)

    deleted: list[str] = []
    missing: list[str] = []
    files_deleted: list[str] = []

    for aid in audio_ids:
        doc = get_audio_document(aid)
        if not doc:
            missing.append(aid)
            continue

        try:
            delete_audio_segments(aid)
        except Exception:
            print(f"删除 {aid} 对应的音频文档失败")

        delete_audio_document(aid)
        deleted.append(aid)

        if req.delete_files:
            try:
                p = Path(str(doc.get("stored_path") or ""))
                if p.exists() and p.is_file():
                    p.unlink()
                    files_deleted.append(aid)
            except Exception:
                print(f"{aid} 对应的磁盘上的文件不存在或 stored_path 错误")

    return BulkDeleteResp(
        deleted=deleted,
        missing=missing,
        vectors_deleted=vectors_deleted,
        files_deleted=files_deleted,
    )


@audio_admin_router.post("/docs/bulk-reindex", response_model=BulkReindexResp)
def bulk_reindex(req: BulkReindexReq):
    """
    批量重嵌入音频文件

    :param req: 批量重建的请求
    :return: BulkReindexResp
    """

    audio_ids = [a.strip() for a in (req.audio_ids or []) if (a or "").strip()]
    if not audio_ids:
        raise HTTPException(status_code=400, detail="audio_ids is empty")

    submitted: list[ReindexItem] = []
    skipped_running: list[str] = []
    missing: list[str] = []

    for aid in audio_ids:
        doc = get_audio_document(aid)
        if not doc:
            missing.append(aid)
            continue

        if is_audio_running(aid):
            skipped_running.append(aid)
            continue

        job_id = f"job-reindex-{aid}"
        create_job(job_id, aid, overwrite=False, delete_old_file=False, old_stored_path=None)

        update_audio_status(aid, "queued")

        async_result = celery_app.send_task(
            "app.tasks.audio_tasks.audio_reindex_task",
            args=[job_id, aid],
            queue=getattr(settings, "celery_audio_queue", "audio"),
        )
        bind_task(job_id, async_result.id)

        submitted.append(
            ReindexItem(
                audio_id=aid,
                job_id=job_id,
                celery_task_id=async_result.id,
                status_url=f"/audio/jobs/{job_id}",
            )
        )

    return BulkReindexResp(submitted=submitted, skipped_running=skipped_running, missing=missing)


@audio_admin_router.post("/chroma/reset", response_model=ResetAudioCollectionResp)
def reset_audio_collection(
        confirm: str = Query(..., description="必须等于 DELETE_AUDIO_COLLECTION 才会执行")
):
    """
    重置音频的 Collection，confirm 必须等于 DELETE_AUDIO_COLLECTION 才会执行

    :param confirm: 发出的确认信息
    :return: ResetAudioCollectionResp
    """
    if confirm != "DELETE_AUDIO_COLLECTION":
        raise HTTPException(status_code=400, detail="请确认删除")

    reset_audio_collection()
    return ResetAudioCollectionResp(ok=True, collection=settings.audio_collection_name)
