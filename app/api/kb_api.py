from typing import Optional
from pathlib import Path
import uuid
import time

from fastapi import UploadFile, APIRouter, File, Form, HTTPException, Depends, Query
import chromadb

from app.api.auth_api import get_current_user
from app.model.auth_model import UserInDB
from app.config import settings
from app.ingestion.loader import (
    load_single_file,
    split_and_enrich_metadata,
    load_docs,
    split_docs,
    batch_chunks
)
from app.deps import get_vs
from app.service.rbac_service import require_permission
from app.constants.rbac import Permission
from app.db_ops.kb_sql import (
    get_kb_document,
    list_kb_documents,
    upsert_kb_document,
    update_kb_document_visibility,
    update_kb_document_chunk_count,
    soft_delete_kb_document
)
from app.model.kb_model import (
    KBDocListItem,
    KBDocDetail,
    KBDocReembedResp,
    KBDocVisibilityUpdateReq
)
from app.rag.chroma_admin import (
    delete_by_doc_id,
    update_visibility_by_doc_id,
    count_by_doc_id,
    get_ids_and_metadatas_by_doc_id
)

kb_router = APIRouter(
    prefix="/kb",
    tags=["知识库管理"],
    dependencies=[
        Depends(require_permission(Permission.PERM_KB_MANAGE_DOCS))
    ]
)


DATA_DOCS_DIR = Path(r"/home/supercao/PycharmProjects/kb_assistant/data/docs")
DATA_DOCS_DIR.mkdir(parents=True, exist_ok=True)            # 若不存在 → 自动递归创建所有目录

# todo： 优化文档
@kb_router.post("/ingest")
async def ingest(
        file: UploadFile = File(...),
        visibility: str = Form("public"),
        doc_id: Optional[str] = Form(None),
        overwrite: bool = Form(False),
        current_user: UserInDB = Depends(get_current_user)
):
    """
    将语料库上传到 chromadb/chroma 的某个 collection 中

    具体步骤如下：
    1. 上传一个文件，并将其保存到磁盘
    2. 将其切块，并给每个切块（Document对象）都增加上 visibility 和 doc_id 的元数据信息
    3. 最后添加到 chroma 数据库中

    :param file: 上传的文件
    :param visibility: 文件的可见性属性
    :param doc_id: 文件 id
    :param overwrite: 是否重写
    :param current_user: 从请求头中获取当前用户
    :return: 保存的路径，可见性，文件id, 分块长度, 是否已重写
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="空文件")

    visibility = (visibility or "public").strip().lower()
    doc_id = (doc_id or f"doc-{uuid.uuid4().hex[:12]}").strip()

    existed = get_kb_document(doc_id)
    if existed and not overwrite:
        raise HTTPException(status_code=409, detail=f"文档ID为 {doc_id} 对应的文档已存在且无需重写")

    if existed and overwrite:
        try:
            delete_by_doc_id(doc_id)
        except Exception as e:
            print(f"删除失败： {e}")
    suffix = Path(file.filename).suffix
    safe_name = f"{int(time.time())}_{uuid.uuid4().hex}{suffix}"
    save_path = DATA_DOCS_DIR / safe_name

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    save_path.write_bytes(content)

    docs = load_single_file(save_path)                                                  # 切块
    if not docs:
        raise HTTPException(status_code=400, detail="文件类型不支持或空文件")

    extra_meta = {
        "original_filename": file.filename,
        "stored_path": str(save_path),
        "uploader_user_id": current_user.id,
        "uploader_username": current_user.username,
        "uploaded_at": int(time.time())
    }

    chunks = split_and_enrich_metadata(
        docs,
        visibility=visibility,
        doc_id=doc_id,
        extra_meta=extra_meta
    )

    vs = get_vs()
    for batch in batch_chunks(chunks, 64):
        vs.add_documents(batch)

    try:
        chroma_cnt = count_by_doc_id(doc_id)
    except Exception:
        chroma_cnt = len(chunks)

    upsert_kb_document(
        doc_id=doc_id,
        original_filename=file.filename,
        stored_path=str(save_path),
        visibility=visibility,
        uploader_user_id=current_user.id,
        uploader_username=current_user.username,
        chunk_count=chroma_cnt
    )

    return {
        "saved_as": str(save_path),
        "visibility": visibility,
        "doc_id": doc_id,
        "chunks": chroma_cnt,
        "overwrote": bool(existed and overwrite)
    }


@kb_router.post("/ingest/batch")
async def ingest_batch(
        files: list[UploadFile] = File(...),
        visibility: str = Form("public"),
        doc_id: Optional[str] = Form(None),
        overwrite: bool = Form(False),
        current_user: UserInDB = Depends(get_current_user)
):
    """
    多文件上传并写入 Chroma

    - 每个文件会生成一个独立 doc_id（除非显式传入）
    - 失败文件不会影响其他文件
    """
    # todo： 此段是AI生成，未测试此接口，考虑简化
    if not files:
        raise HTTPException(status_code=400, detail="未上传文件")

    visibility = (visibility or "public").strip().lower()

    results = []

    for file in files:
        if not file.filename:
            results.append({
                "filename": None,
                "status": "failed",
                "reason": "空文件名"
            })
            continue

        # ========== doc_id 策略 ==========
        # 1. 如果用户传 doc_id → 所有文件共用（不推荐）
        # 2. 不传 → 每个文件生成一个
        _doc_id = (doc_id or f"doc-{uuid.uuid4().hex[:12]}").strip()

        try:
            existed = get_kb_document(_doc_id)
            if existed and not overwrite:
                raise HTTPException(
                    status_code=409,
                    detail=f"文档ID {_doc_id} 已存在"
                )

            if existed and overwrite:
                delete_by_doc_id(_doc_id)

            suffix = Path(file.filename).suffix
            safe_name = f"{int(time.time())}_{uuid.uuid4().hex}{suffix}"
            save_path = DATA_DOCS_DIR / safe_name

            content = await file.read()
            if not content:
                raise ValueError("空文件内容")

            save_path.write_bytes(content)

            docs = load_single_file(save_path)
            if not docs:
                raise ValueError("文件类型不支持或空文件")

            extra_meta = {
                "original_filename": file.filename,
                "stored_path": str(save_path),
                "uploader_user_id": current_user.id,
                "uploader_username": current_user.username,
                "uploaded_at": int(time.time())
            }

            chunks = split_and_enrich_metadata(
                docs,
                visibility=visibility,
                doc_id=_doc_id,
                extra_meta=extra_meta
            )

            vs = get_vs()
            for batch in batch_chunks(chunks, 64):
                vs.add_documents(batch)

            try:
                chroma_cnt = count_by_doc_id(_doc_id)
            except Exception:
                chroma_cnt = len(chunks)

            upsert_kb_document(
                doc_id=_doc_id,
                original_filename=file.filename,
                stored_path=str(save_path),
                visibility=visibility,
                uploader_user_id=current_user.id,
                uploader_username=current_user.username,
                chunk_count=chroma_cnt
            )

            results.append({
                "filename": file.filename,
                "doc_id": _doc_id,
                "chunks": chroma_cnt,
                "saved_as": str(save_path),
                "status": "success",
                "overwrote": bool(existed and overwrite)
            })

        except Exception as e:
            results.append({
                "filename": file.filename,
                "doc_id": _doc_id,
                "status": "failed",
                "reason": str(e)
            })

    return {
        "visibility": visibility,
        "total": len(files),
        "success": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results
    }


@kb_router.post("/reindex")
def reindex(visibility_default: str = Form("public")):
    """
    带上默认的可见性信息，全量重建语料库

    :param visibility_default: 默认的可见性
    :return: 文件长度，切块长度和默认可见性的信息
    """
    visibility_default = (visibility_default or "public").strip().lower()

    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    try:
        client.delete_collection(settings.collection_name)
    except Exception:
        print(f"e:{Exception.__name__}")

    client.get_or_create_collection(settings.collection_name)

    vs = get_vs()
    raw_docs = load_docs(str(DATA_DOCS_DIR))
    if not raw_docs:
        return {"chunks": 0, "docs": 0, "messages": "在data/docs下没找到任何文件"}

    chunks = split_docs(raw_docs)
    for c in chunks:
        c.metadata = dict(c.metadata or {})
        c.metadata.setdefault("visibility", visibility_default)

    vs.add_documents(chunks)

    return {"docs": len(raw_docs), "chunks": len(chunks), "visibility_default": visibility_default}


@kb_router.get("/list_docs", response_model=list[KBDocListItem])
def list_docs(
        visibility: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        include_chroma_count: bool = Query(default=False)
):
    """ 列出满足条件的文档，筛选条件为 limit, offset, visibility 和 include_chroma_count """
    rows = list_kb_documents(limit=limit, offset=offset, visibility=visibility)

    out: list[dict] = []
    for r in rows:
        item = dict(r)
        if include_chroma_count:
            item["chroma_chunk_count"] = count_by_doc_id(item["doc_id"])
        out.append(item)
    return out


@kb_router.get("/docs/{doc_id}", response_model=KBDocDetail)
def get_doc_by_doc_id(
        doc_id: str,
        include_chroma_count: bool = Query(default=True)
):
    """ 根据 doc_id 获取文档 """
    row = get_kb_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"文档ID为 {doc_id} 对应的文档未找到")

    data = dict(row)
    data["chroma_chunk_count"] = count_by_doc_id(doc_id) if include_chroma_count else 0
    return data


@kb_router.patch("/docs/{doc_id}/visibility", response_model=KBDocDetail)
def update_doc_visibility(
        doc_id: str,
        req: KBDocVisibilityUpdateReq
):
    """ 根据 doc_id 修改文档"""
    row = get_kb_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"文档ID为 {doc_id} 对应的文档未找到")

    visibility = (req.visibility or "").strip().lower()
    if not visibility:
        raise HTTPException(status_code=400, detail="文档需要可见性")

    updated = update_visibility_by_doc_id(doc_id, visibility)
    update_kb_document_visibility(doc_id, visibility)
    update_kb_document_chunk_count(doc_id, count_by_doc_id(doc_id))

    new_row = get_kb_document(doc_id) or {}
    data = dict(new_row)
    data["chroma_chunk_count"] = updated
    return data


@kb_router.delete("/docs/{doc_id}")
def delete_doc(
        doc_id: str,
        delete_file: bool = Query(default=False)
):
    """ 根据 doc_id 删除文档 """
    row = get_kb_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"文档ID为 {doc_id} 对应的文档未找到")

    deleted_chunks = delete_by_doc_id(doc_id)
    soft_delete_kb_document(doc_id)

    deleted_file = False
    if delete_file:
        try:
            p = Path(row["stored_path"])
            if p.exists() and p.is_file():
                p.unlink()
                deleted_file = True
        except Exception:
            deleted_file = False

    return {
        "ok": True,
        "doc_id": doc_id,
        "deleted_chunks": deleted_chunks,
        "deleted_file": deleted_file
    }


@kb_router.post("/docs/{doc_id}/reembed", response_model=KBDocReembedResp)
def reembed_doc(doc_id: str):
    """ 根据 doc_id 重嵌入文档 """
    row = get_kb_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"文档ID为为为 {doc_id} 对应的文档未找到")

    stored_path = Path(row["stored_path"])
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail=f"对应的 {stored_path} 路径下无文档")

    deleted = delete_by_doc_id(doc_id)

    docs = load_single_file(stored_path)
    if not docs:
        raise HTTPException(status_code=400, detail="文件格式仅支持 .pdf/.doc/.docx/.txt/.md")

    visibility = (row.get("visibility") or "public").strip().lower()
    extra_meta = {
        "original_filename": row.get("original_filename"),
        "stored_path": str(stored_path),
        "uploader_user_id": row.get("uploader_user_id"),
        "uploader_username": row.get("uploader_username")
    }

    chunks = split_and_enrich_metadata(docs, visibility, doc_id, extra_meta)

    vs = get_vs()
    vs.add_documents(chunks)


    new_count = count_by_doc_id(doc_id)
    print(f"==-------------------{new_count}======================")
    update_kb_document_chunk_count(doc_id, new_count)
    update_kb_document_visibility(doc_id, visibility)

    return KBDocReembedResp(doc_id=doc_id, deleted_chunks=deleted, new_chunks=new_count, visibility=visibility)
