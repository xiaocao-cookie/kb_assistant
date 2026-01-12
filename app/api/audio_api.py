from pathlib import Path
from typing import Optional
import uuid
import time
import httpx

from fastapi import (APIRouter,
                     HTTPException,
                     Query,
                     UploadFile,
                     File,
                     Form,
                     Depends,
                     BackgroundTasks,
                     Request)
from fastapi.responses import FileResponse
from langchain_core.documents import Document

from app.deps import get_audio_vs
from app.service.rbac_service import (
    require_permission,
    get_current_user,
    compute_user_allowed_visibilities
)
from app.constants.rbac import Permission
from app.model.audio_model import (
    AudioDocDetail,
    AudioSearchHit,
    AudioSearchResp,
    AudioIngestResp,
    AudioAskResp,
    AudioAskReq,
    AudioCitation
)
from app.db_ops.audio_sql import (
    get_audio_document,
    upsert_audio_document,
    replace_audio_segments,
    get_audio_segment,
    is_audio_running
)
from app.rag.audio_retrieve import audio_similarity_search
from app.model.auth_model import UserInDB
from app.utils.clip_audio import clip_audio_to_mp3
from app.config import settings
from app.db_ops.audio_job_sql import (
    create_job,
    bind_task,
    get_job,
    request_cancel
)
from app.tasks.audio_tasks import audio_ingest_task
from app.model.audio_model import AudioIngestAsyncResp
from app.model.audio_job_model import AudioJobResp
from app.utils.path_utils import ensure_dir
from app.utils.visibility_validation import parse_visibility
from app.utils.completion import deepseek_chat_completion


audio_router = APIRouter(
    prefix="/audio",
    tags=["音频处理路由"],
    dependencies=
    [
        Depends(require_permission(Permission.PERM_KB_MANAGE_DOCS)),
     ]
)


# todo: 此模块考虑添加一个 音频知识库 重建功能


def _clip_url(
        base: str,
        audio_id: str,
        start_ms: int,
        end_ms: int
) -> str:
    """ 音频裁剪的链接 """
    return f"{base}/audio/docs/{audio_id}/clip?start_ms={start_ms}&end_ms={end_ms}"


def _build_rag_messages(question: str,
                        citations: list[AudioCitation],
                        system_prompt: Optional[str]
                        ) -> list[dict[str, str]]:
    """
    构造用于 RAG 场景的 messages

    :param question: 用户询问的问题
    :param citations: 检索出的音频片段信息
    :param system_prompt: 系统提示词
    :return: LLM 的 messages
    """

    sys = (system_prompt or "").strip() or (
        "你是企业知识库助手，回答必须基于给定的【音频片段】内容。"
        "如果片段不足以回答，就明确说“不确定/片段中没有”。"
        "回答要简洁，并在结尾给出引用列表（用 [1][2]... 标注）。"
    )

    ctx_lines: list[str] = []
    for i, c in enumerate(citations, start=1):
        ctx_lines.append(
            f"[{i}] audio_id={c.audio_id} segment_id={c.segment_id} "
            f"start_ms={c.start_ms} end_ms={c.end_ms}\n"
            f"片段文本：{c.text}"
        )
    ctx = "\n\n".join(ctx_lines) if ctx_lines else "（无片段）"

    user = (
        f"问题：{question}\n\n"
        f"【音频片段】\n{ctx}\n\n"
        "要求：\n"
        "1) 只用片段信息回答。\n"
        "2) 如果引用了某个片段，请用 [序号] 标注。\n"
        "3) 不要编造片段里没有的信息。"
    )

    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]


@audio_router.post("/ingest", response_model=AudioIngestAsyncResp)
async def ingest_audio(
        file: UploadFile = File(...),
        visibility: str = Form("public"),
        audio_id: Optional[str] = Form(None),
        language: Optional[str] = Form(None),
        overwrite: bool = Form(False),
        delete_old_file: bool = Form(False),
        current_user: UserInDB = Depends(get_current_user)
):
    """
    此函数实现了异步上传音频文件，分为以下几步：
    1. 上传一个音频文件，并将其保存到磁盘
    2. 将音频文件的一些元数据 upsert 到 audio_documents 表中
    3. 向 audio_jobs 表中新增音频文件上传的任务
    4. celery 异步任务调用，并将 celery 的任务 ID 与 audio_jobs 表中的 job_id 绑定
    5. 返回音频异步上传的响应体

    :param file: 原文件
    :param visibility: 可见性
    :param audio_id: 音频 ID
    :param language: 音频的语言
    :param overwrite: 是否重写
    :param delete_old_file: 是否删除旧文件
    :param current_user: 当前登录用户
    :return: AudioIngestAsyncResp，音频嵌入的异步响应体
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    visibility = parse_visibility(visibility)
    audio_id = (audio_id or f"aud-{uuid.uuid4().hex[:12]}").strip()
    job_id = f"job-{uuid.uuid4().hex[:12]}"

    if is_audio_running(audio_id):
        raise HTTPException(status_code=409, detail=f"该音频在消息队列中不是 RUNNING 状态")

    row = get_audio_document(audio_id)
    if row and not overwrite:
        raise HTTPException(status_code=409, detail="该音频已存在，若想重写，请设置 overwrite=True")

    old_stored_path = row["stored_path"] if row else None

    ensure_dir(settings.AUDIO_DIR)
    suffix = Path(file.filename).suffix or ".bin"
    raw_path = settings.AUDIO_DIR / f"{int(time.time())}_{uuid.uuid4().hex}{suffix}"
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="文件中无内容")
    raw_path.write_bytes(raw_bytes)

    upsert_audio_document(
        audio_id=audio_id,
        original_filename=file.filename,
        stored_path=str(raw_path),
        duration_ms=0,
        language=language,
        visibility=visibility,
        status="queued",
        uploader_user_id=int(getattr(current_user, "id", 0) or 0) or None,
        uploader_username=getattr(current_user, "username", None),
        segment_count=0
    )

    create_job(
        job_id,
        audio_id,
        overwrite=bool(overwrite),
        delete_old_file=bool(delete_old_file),
        old_stored_path=old_stored_path if overwrite else None
    )

    async_result = audio_ingest_task.apply_async(
        args=[job_id, audio_id],
        queue=getattr(settings, "celery_audio_queue", "audio")
    )

    bind_task(job_id, async_result.id)

    return AudioIngestAsyncResp(
        job_id=job_id,
        audio_id=audio_id,
        stored_as=str(raw_path),
        visibility=visibility,
        celery_task_id=async_result.id,
        status_url=f"/audio/jobs/{job_id}",
    )


@audio_router.get("/query", response_model=AudioSearchResp)
def query_audio(
        request: Request,
        q: str = Query(..., min_length=1),
        k: int = Query(default=6, ge=1, le=20),
        current_user: UserInDB = Depends(get_current_user)
):
    """
    查询与 q 最近的 fetch_k 个向量（文档）
    fetch_k 的计算公式为： $ min(max(k * 5, k), 50) $

    :param request: HTTP 的请求对象
    :param q: 查询键
    :param k: 最邻近的 k 个
    :param current_user: 当前登录用户
    :return: AudioSearchResp
    """

    fetch_k = min(max(k * 5, k), 50)

    allowed_vis = compute_user_allowed_visibilities(current_user)
    allowed_vis_set = set(allowed_vis)

    where = {"visibility": {"$in": allowed_vis}}

    docs_scores = audio_similarity_search(q, k=fetch_k, where=where)

    base_url = str(request.base_url).rstrip("/")

    hits: list[AudioSearchHit] = []
    seen: set[tuple[str, str, int, int]] = set()

    for doc, score in docs_scores:
        m = doc.metadata or {}

        audio_id = str(m.get("audio_id", "") or "").strip()
        segment_id = str(m.get("segment_id", "") or "").strip()
        start_ms = int(m.get("start_ms", 0) or 0)
        end_ms = int(m.get("end_ms", 0) or 0)
        texts = (doc.page_content or "").strip()

        if audio_id and end_ms > start_ms:
            clip_url = _clip_url(base_url, audio_id, start_ms, end_ms)
        else:
            continue

        key = (audio_id, segment_id, start_ms, end_ms)
        if key in seen:
            continue
        seen.add(key)

        audio_doc = get_audio_document(audio_id)
        if not audio_doc:
            continue

        doc_vis = (audio_doc.get("visibility") or "").strip().lower()
        if doc_vis not in allowed_vis_set:
            continue

        hits.append(
            AudioSearchHit(
                audio_id=audio_id,
                segment_id=segment_id,
                start_ms=start_ms,
                end_ms=end_ms,
                texts=texts,
                score=float(score) if score is not None else None,
                clip_url=clip_url
            )
        )
        if len(hits) >= k:
            break

    return AudioSearchResp(q=q, k=k, allowed_visibilities=allowed_vis, hits=hits)


@audio_router.post("/ask", response_model=AudioAskResp)
def ask_audio(
        request: Request,
        req: AudioAskReq,
        current_user: UserInDB = Depends(get_current_user)
):
    """
    使用 req 中的参数调用 LLM 生成回复
    req 中包含：
         1. question: 用户询问的问题
         2. k: 最邻近的 k 个向量
         3. audio_id: 音频 ID
         4. system_prompt: 系统的提示词

    这里有一点需要说明的是：
    在向量的相似性搜索下，这里搜索的是与 question 最相关的 **fetch_k** 个向量，且指定仅搜索 audio_id下的向量
    其中，fetch_k 的计算公式如下：
        $$
            fetch_k = min(max(k * 5, k), 50)
        $$

    :param request: FastAPI 的 Request 对象
    :param req: 请求体的 Model
    :param current_user: 当前登录用户
    :return: AudioAskResp
    """

    question = (req.question or "").strip()
    k = req.k

    base_url = str(request.base_url).rstrip("/")

    allowed_vis = compute_user_allowed_visibilities(current_user)
    allowed_vis_set = set(allowed_vis)

    where = {"visibility": {"$in": allowed_vis}}
    if req.audio_id:
        where = {"$and": [
            {"visibility": {"$in": allowed_vis}},
            {"audio_id": req.audio_id},
        ]}

    fetch_k = min(max(k * 5, k), 50)

    docs_scores = audio_similarity_search(question, k=fetch_k, where=where)

    citations: list[AudioCitation] = []
    seen: set[tuple[str, str, int, int]] = set()

    for doc, score in docs_scores:
        md = doc.metadata or {}
        audio_id = str(md.get("audio_id") or "").strip()
        segment_id = str(md.get("segment_id") or "").strip()
        start_ms = int(md.get("start_ms") or 0)
        end_ms = int(md.get("end_ms") or 0)

        # 去重处理
        key = (audio_id, segment_id, start_ms, end_ms)
        if key in seen:
            continue
        seen.add(key)

        audio_doc = get_audio_document(audio_id)
        if not audio_doc:
            continue

        doc_vis = (audio_doc.get("visibility") or "").strip()
        if doc_vis not in allowed_vis_set:
            continue

        text = (doc.page_content or "").strip()
        citations.append(
            AudioCitation(
                audio_id=audio_id,
                segment_id=segment_id,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                clip_url=_clip_url(base_url, audio_id, start_ms, end_ms),
                score=float(score) if score is not None else None,
            )
        )
        if len(citations) >= k:
            break

    if not citations:
        return AudioAskResp(question=question, answer="没有检索到相关音频片段。", citations=[])

    api_key = settings.openai_api_key
    model = settings.model_name

    if not api_key:
        return AudioAskResp(
            question=question,
            answer="(未配置 OPENAI_API_KEY) 已返回相关音频片段引用，可先基于citations手动判断。",
            citations=citations,
        )

    messages = _build_rag_messages(question, citations, req.system_prompt)
    answer = deepseek_chat_completion(
        model=model,
        api_key=api_key,
        temperature=0,
        messages=messages,
        timeout_s=90.0,
        stream=True
    )

    return AudioAskResp(question=question, answer=answer, citations=citations)



@audio_router.get("/{audio_id}", response_model=AudioDocDetail)
def get_audio(audio_id: str):
    """
    通过 audio_id 获取音频信息

    :param audio_id: 音频 ID
    :return: AudioDocDetail，音频信息
    """

    row = get_audio_document(audio_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Audio_id 为 {audio_id} 的数据未找到")

    return row


@audio_router.get("/{audio_id}/clip")
def get_audio_clip(
        audio_id: str,
        background_tasks: BackgroundTasks,
        start_ms: Optional[int] = Query(default=None, ge=0),
        end_ms: Optional[int] = Query(default=None, ge=0),
        max_clip_ms: int = 300_000,
        segment_id: Optional[str] = Query(default=None)
):
    """
    首先，通过 audio_id 查询音频
    接下来，
        - 如果segment_id 给出，将这段音频按照 segment_id 裁剪成 MP3
        - 如果 segment_id 未给出，则根据 start_ms 和 end_ms 裁剪音频，最大裁剪时长由 max_clip_ms 指定
    最后，裁剪成功并且在服务端发出响应之后进行 background_tasks


    :param audio_id: 音频 ID
    :param background_tasks: 后台任务（服务端响应成功发送之后执行）
    :param start_ms: 开始的毫秒数，当 segment_id 为 None 时必须指定
    :param end_ms: 结束的毫秒数，当 segment_id 为 None 时必须指定
    :param max_clip_ms: 最大的裁剪时长（毫秒），默认 5 分钟（300_000 毫秒）
    :param segment_id: 音频分段的 ID，格式应为 "audio_id:segment_index"
    :return: FileResponse, 文件的“流式”响应
    """

    row = get_audio_document(audio_id)
    if not row:
        raise HTTPException(status_code=404, detail="音频未找到")

    if segment_id:
        if ":" not in segment_id:
            raise HTTPException(status_code=400, detail="无效的分割模式")
        seg_audio_id, seg_idx_str = segment_id.split(":", 1)
        if seg_audio_id != audio_id:
            raise HTTPException(status_code=400, detail="该音频无这段分割信息")
        try:
            seg_idx = int(seg_idx_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的分割ID，它必须是整数")

        seg = get_audio_segment(audio_id, seg_idx)
        if not seg:
            raise HTTPException(status_code=404, detail="音频分段未找到")

        start_ms = int(seg["start_ms"])
        end_ms = int(seg["end_ms"])
    else:
        if start_ms is None or end_ms is None:
            raise HTTPException(status_code=400, detail="无 segment_id 时需提供开始和结束时间")

    if end_ms <= start_ms:
        raise HTTPException(status_code=400, detail="结束时间必须大于开始时间")

    if (end_ms - start_ms) > max_clip_ms:
        raise HTTPException(status_code=400, detail=f"裁剪时间不能超过 {int(max_clip_ms / 1000)} s")

    src_path = Path(row["stored_path"])
    if not src_path.exists():
        raise HTTPException(status_code=400, detail="磁盘上存储的音频文件丢失")

    ensure_dir(settings.CLIP_DIR)
    clip_name = f"{audio_id}_{start_ms}_{end_ms}_{uuid.uuid4().hex[:8]}.mp3"
    clip_path = settings.CLIP_DIR / clip_name

    try:
        clip_audio_to_mp3(
            src_path=src_path,
            dst_path=clip_path,
            start_ms=int(start_ms),
            end_ms=int(end_ms)
        )
    except Exception:
        raise HTTPException(status_code=500, detail="裁剪失败")

    background_tasks.add_task(lambda p=str(clip_path): Path(p).unlink(missing_ok=True))

    return FileResponse(
        path=str(clip_path),
        media_type="audio/mpeg",
        filename=clip_name
    )


@audio_router.get("/jobs/{job_id}", response_model=AudioJobResp)
def get_audio_job(job_id: str):
    """
    通过 job_id 获取对应的音频入库任务的信息

    :param job_id: 任务 ID
    :return: AudioJobResp
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"任务ID {job_id} 对应的任务不存在")
    return row


@audio_router.post("/jobs/{job_id}/cancel")
def cancel_audio_job(job_id: str):
    """
    根据 job_id 将对应任务的 cancel_requested 字段设置为 1

    :param job_id:
    :return:
    """

    ok = request_cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务未找到")
    return {"job_id": job_id, "cancel_requested": True}
