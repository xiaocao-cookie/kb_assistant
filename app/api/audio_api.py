from pathlib import Path
from typing import Optional
import uuid
import time

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
    replace_audio_segments,
    get_audio_segment
)
from app.rag.audio_retrieve import audio_similarity_search_for_user
from app.ingestion.audio_loader import transcode_to_wav_16k_mono, ffprobe_duration_ms
from app.utils.asr import ASR
from app.utils.audio_segmenter import merge_by_max_duration
from app.ingestion.doc_loader import batch_chunks
from app.model.auth_model import UserInDB
from app.utils.clip_audio import clip_audio_to_mp3


audio_router = APIRouter(
    prefix="/audio",
    tags=["音频检索路由"],
    dependencies=
    [
        Depends(require_permission(Permission.PERM_KB_MANAGE_DOCS)),
     ]
)


AUDIO_DIR = Path("data/audio")      # todo: 作 OS 对象存储
AUDIO_WAV_DIR = Path("data/audio_wav")
CLIP_DIR = Path("data/audio_clips")     # todo： 作对象存储


@audio_router.post("/ingest", response_model=AudioIngestResp)
async def ingest_audio(
        file: UploadFile = File(...),
        audio_id: Optional[str] = Form(None),
        language: Optional[str] = Form(None),
        current_user: UserInDB = Depends(get_current_user)
):
    """
    此函数实现了以下三个功能：
    1. 上传一个音频文件，并将其保存到磁盘
    2. 将音频转成文本并存储到 Chroma 中名为 audio_base 的 collection 中
    3. 将文件的一些元数据 upsert 到 audio_documents 的数据库中

    :param file: 原文件
    :param audio_id: 音频 ID
    :param language: 音频的语言
    :param current_user: 当前登录用户
    :return: AudioIngestResp
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

    vs = get_audio_vs()

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

    for batch in batch_chunks(docs, 64):
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

# todo: 写文档
@audio_router.get("/search", response_model=AudioSearchResp)
def search_audio(
        request: Request,
        q: str = Query(..., min_length=1),
        k: int = Query(default=6, ge=1, le=20)
):
    """
    查询与 q 最近的 k 个向量（文档）

    :param request:
    :param q: 查询键
    :param k: 最邻近的 k 个
    :return: AudioSearchResp
    """

    docs, allowed = audio_similarity_search_for_user(q, k=k)

    base_url = str(request.base_url).rstrip("/")

    hits: list[AudioSearchHit] = []

    for d in docs:
        m = d.metadata or {}

        audio_id = str(m.get("audio_id", "") or "")
        segment_id = str(m.get("segment_id", "") or "")
        start_ms = int(m.get("start_ms", 0) or 0)
        end_ms = int(m.get("end_ms", 0) or 0)

        if audio_id and end_ms > start_ms:
            clip_url = f"{base_url}/audio/{audio_id}/clip?start_ms={start_ms}&end_ms={end_ms}"
        else:
            raise HTTPException(status_code=400, detail=f"{audio_id} 不存在或开始时间大于结束时间")

        hits.append(
            AudioSearchHit(
                audio_id=audio_id,
                segment_id=segment_id,
                start_ms=start_ms,
                end_ms=end_ms,
                texts=d.page_content,
                score=None,
                clip_url=clip_url
            )
        )

    return AudioSearchResp(q=q, k=k, allowed_visibilities=allowed, hits=hits)


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

# todo: 是否加 current_user
@audio_router.get("/{audio_id}/clip")
def get_audio_clip(
        audio_id: str,
        background_tasks: BackgroundTasks,
        start_ms: Optional[int] = Query(default=None, ge=0),
        end_ms: Optional[int] = Query(default=None, ge=0),
        segment_id: Optional[str] = Query(default=None)
):
    """


    :param audio_id:
    :param background_tasks:
    :param start_ms:
    :param end_ms:
    :param segment_id:
    :return:
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

    max_clip_ms = 5 * 60 * 1000
    if (end_ms - start_ms) > max_clip_ms:
        raise HTTPException(status_code=400, detail=f"裁剪时间不能超过 {int(max_clip_ms / 1000)} s")

    src_path = Path(row["stored_path"])
    if not src_path.exists():
        raise HTTPException(status_code=400, detail="磁盘上存储的音频文件丢失")

    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    clip_name = f"{audio_id}_{start_ms}_{end_ms}_{uuid.uuid4().hex[:8]}.mp3"
    clip_path = CLIP_DIR / clip_name

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


