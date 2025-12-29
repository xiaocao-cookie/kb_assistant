from pathlib import Path
from typing import Optional
import uuid
import time

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Depends
from langchain_core.documents import Document

from app.deps import get_vs
from app.service.rbac_service import require_permission, get_current_user
from app.constants.rbac import Permission
from app.model.audio_model import (
    AudioDocDetail,
    AudioSearchHit,
    AudioSearchResp,
    AudioIngestResp
)
from app.db_ops.audio_sql import (
    get_audio_document,
    upsert_audio_document,
    replace_audio_segments
)
from app.rag.audio_retrieve import audio_similarity_search_for_user
from app.ingestion.audio_loader import transcode_to_wav_16k_mono, ffprobe_duration_ms
from app.ingestion.asr import ASR
from app.ingestion.audio_segmenter import merge_by_max_duration
from app.ingestion.doc_loader import batch_chunks
from app.model.auth_model import UserInDB


audio_router = APIRouter(
    prefix="/audio",
    tags=["音频检索路由"],
    dependencies=require_permission(Permission.PERM_KB_MANAGE_DOCS)
)


AUDIO_DIR = Path("data/audio")      # todo: 作 OS 对象存储
AUDIO_WAV_DIR = Path("data/audio_wav")

# todo: 写注释文档
@audio_router.post("/ingest", response_model=AudioIngestResp)
async def ingest_audio(
        file: UploadFile = File(...),
        audio_id: Optional[str] = Form(None),
        language: Optional[str] = Form(None),
        current_user: UserInDB = Depends(get_current_user)
):
    """

    :param file:
    :param audio_id:
    :param language:
    :param current_user:
    :return:
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    visibility = "public"
    audio_id = (audio_id or f"aud-{uuid.uuid4().hex[:12]}").strip()

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix or ".bin"
    raw_path = AUDIO_DIR / f"{int(time.time())}_{uuid.uuid4().hex}{suffix}"
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="文件中无内容")
    raw_path.write_bytes(raw_bytes)

    AUDIO_WAV_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = AUDIO_WAV_DIR / f"{audio_id}.wav"
    transcode_to_wav_16k_mono(raw_path, wav_path)

    duration_ms = ffprobe_duration_ms(wav_path)

    asr = ASR(model_name="base", device="cpu", compute_type="int8")
    asr_segs, detected_lang = asr.transcribe(str(wav_path), language=language)
    lang = language or detected_lang

    chunks = merge_by_max_duration(asr_segs, max_ms=25_000, min_ms=6_000)

    vs = get_vs()               # todo: 需修改

    docs: list[Document] = []
    segment_rows: list[dict] = []
    for idx, c in enumerate(chunks):
        seg_id = f"{audio_id}:{idx}"
        text = c.text.strip()
        if not text:
            continue

        meta = {
            "doc_type": "audio",
            "audio_id": audio_id,
            "segment_id": seg_id,
            "segment_idx": idx,
            "start_ms": c.start_ms,
            "end_ms": c.end_ms,
            "visibility": visibility,
            "original_filename": file.filename,
            "stored_path": str(raw_path),
            "wav_path": str(wav_path),
            "language": lang,
        }
        docs.append(Document(page_content=text, metadata=meta))
        segment_rows.append(
            {"segment_idx": idx, "start_ms": c.start_ms, "end_ms": c.end_ms, "text": text}
        )

    if not docs:
        raise HTTPException(status_code=400, detail="无转换")

    for batch in batch_chunks(chunks, 64):
        vs.add_documents(batch)

    upsert_audio_document(
        audio_id=audio_id,
        original_filename=file.filename,
        stored_path=str(raw_path),
        duration_ms=duration_ms,
        language=lang,
        visibility=visibility,
        status="indexed",
        uploader_user_id=int(current_user.id),
        uploader_username=current_user.username,
        segment_count=len(segment_rows),
    )

    replace_audio_segments(audio_id, segment_rows)

    return AudioIngestResp(
        audio_id=audio_id,
        stored_as=str(raw_path),
        duration_ms=duration_ms,
        language=lang,
        visibility=visibility,
        segments=len(segment_rows),
    )


@audio_router.get("/search", response_model=AudioSearchResp)
def search_audio(
        q: str = Query(..., min_length=1),
        k: int = Query(default=6, ge=1, le=20)
):
    """

    :param q:
    :param k:
    :return:
    """
    docs, allowed = audio_similarity_search_for_user(q, k=k)

    hits: list[AudioSearchHit] = []

    for d in docs:
        m = d.metadata or {}
        hits.append(
            AudioSearchHit(
                audio_id=str(m.get("audio_id", "")),
                segment_id=str(m.get("segment_id", "")),
                start_ms=int(m.get("start_ms", 0)),
                end_ms=int(m.get("end_ms", 0)),
                texts=d.page_content,
                score=None
            )
        )

    return AudioSearchResp(q=q, k=k, allowed_visibilities=allowed, hits=hits)


@audio_router.get("/{audio_id}", response_model=AudioDocDetail)
def get_audio(audio_id: str):
    """

    :param audio_id:
    :return:
    """
    row = get_audio_document(audio_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Audio_id 为 {audio_id} 的数据未找到")

    return row

