from pathlib import Path
from typing import Optional, Any, Dict, Callable, List
from dataclasses import dataclass
import math
import logging

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from langchain_core.documents import Document
import webrtcvad

from app.config import settings
from app.ingestion.audio_loader import ffprobe_duration_ms, transcode_to_wav_16k_mono
from app.ingestion.doc_loader import batch_chunks
from app.db_ops import audio_sql
from app.deps import get_audio_vs

# todo: 补充文档
ProgressFn = Callable[[int, str], None]

@dataclass
class SpeechSeg:
    start_ms: int
    end_ms: int


@dataclass
class AsrSeg:
    start_ms: int
    end_ms: int
    text: str


def _prog(cb: Optional[ProgressFn], p: int, m: str, length: int = 20) -> None:
    """
    显示带进度条的日志

    :param cb: 回调函数
    :param p: 百分比 0-100
    :param m: 消息
    :param length: 进度条长度（字符数）
    """
    # 计算完成块数
    done_blocks = int(p / 100 * length)
    GREEN = "\033[92m"
    RESET = "\033[0m"
    bar = GREEN + "#" * done_blocks + RESET + "-" * (length - done_blocks)
    msg = f"\n[{bar}] {p:3d}% {m}\n"

    if cb:
        cb(int(p), str(m))

    # 直接打印到日志
    logging.getLogger("app.tasks.audio_tasks").info(msg)



def _read_wav_mono_16k(path: Path) -> np.ndarray:
    """
    将 path 下的音频文件读取为对应 NumPy 下的 ndarray
    该音频文件应该是单声道和 16KHz 的采样率

    :param path: 文件路径
    :return: 该文件转成的 NumPy 数组
    """

    audio_data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if sample_rate != settings.TARGET_SR:
        raise RuntimeError(f"采样率应该是 {settings.TARGET_SR}, 而不是 {sample_rate}")
    if isinstance(audio_data, np.ndarray) and audio_data.ndim == 2:
        audio_data = audio_data.mean(axis=1)
    return np.asarray(audio_data, dtype=np.float32)


def _float_to_pcm16_bytes(x: np.ndarray) -> bytes:
    """
    将浮点音频波形 x 裁剪到 `[-1.0, 1.0]` 范围内，并将此音频波形转换成 16-bit PCM 的原始字节流

    :param x:
    :return:
    """

    x = np.clip(x, -1.0, 1.0)
    pcm = (x * 32767.0).astype(np.int16)
    return pcm.tobytes()


def _load_asr_model() -> WhisperModel:
    """
    加载 ASR 模型，返回 WhisperModel 的实例
    """

    return WhisperModel(
        settings.ASR_MODEL,
        device=settings.ASR_DEVICE,
        compute_type=settings.ASR_COMPUTE_TYPE
    )


def _ends_with_punc(t: str) -> bool:
    """


    :param t:
    :return:
    """
    t = (t or "").strip()
    if not t:
        return False
    return t[-1] in settings.PUNCT_END


def _vs_add(vs: Any, docs: list[Document], ids: list[str]) -> None:
    """
    vs 可以通过 add_documents/add_texts 方法，将 docs 添加到对应的向量数据库中，并附带 ids 信息

    :param vs: 向量存储的对象
    :param docs: 要存储的文档
    :param ids: 文档的唯一标识
    """

    if hasattr(vs, "add_documents"):
        for batch_doc in batch_chunks(docs, 64):
            vs.add_documents(batch_doc, ids=ids)
            return
    texts = [d.page_content for d in docs]
    metas = [d.metadata for d in docs]
    if hasattr(vs, "add_texts"):
        for batch in batch_chunks(texts, 64):
            vs.add_texts(batch, metadatas=metas, ids=ids)
            return
    raise RuntimeError("向量存储的对象不支持 add_documents/add_texts 方法")


def _db_replace_segments(audio_id: str, rows: list[dict[str, Any]]) -> None:
    """


    :param audio_id:
    :param rows:
    :return:
    """

    if hasattr(audio_sql, "replace_audio_segments"):
        audio_sql.replace_audio_segments(audio_id, rows)
        return

    raise AttributeError("audio_sql 中无 replace_audio_segments 方法")


def detect_speech_segments(wav_path: Path) -> list[SpeechSeg]:
    """


    :param wav_path:
    :return:
    """

    audio_ndarray = _read_wav_mono_16k(wav_path)
    pcm_bytes = _float_to_pcm16_bytes(audio_ndarray)

    vad = webrtcvad.Vad(settings.VAD_MODE)

    frame_len = int(settings.TARGET_SR * (settings.VAD_FRAME_MS / 1000.0))
    frame_bytes = frame_len * 2
    total_frames = len(pcm_bytes) // frame_bytes

    def is_speech(i: int) -> bool:
        start = i * frame_bytes
        chunk = pcm_bytes[start:start + frame_bytes]
        if len(chunk) < frame_bytes:
            return False
        return vad.is_speech(chunk, sample_rate=settings.TARGET_SR)

    speech_frames: list[tuple[int, int]] = []
    in_speech = False
    seg_start = 0

    for i in range(total_frames):
        sp = is_speech(i)
        if sp and not in_speech:
            in_speech = True
            seg_start = i
        elif (not sp) and in_speech:
            in_speech = False
            speech_frames.append((seg_start, i))

    if in_speech:
        speech_frames.append((seg_start, total_frames))

    pad_frames = int(math.ceil(settings.VAD_PADDING_MS / settings.VAD_FRAME_MS))
    out: List[SpeechSeg] = []
    for a, b in speech_frames:
        a2 = max(0, a - pad_frames)
        b2 = min(total_frames, b + pad_frames)
        start_ms = int(a2 * settings.VAD_FRAME_MS)
        end_ms = int(b2 * settings.VAD_FRAME_MS)
        if (end_ms - start_ms) >= settings.VAD_MIN_SPEECH_MS:
            out.append(SpeechSeg(start_ms=start_ms, end_ms=end_ms))

    if not out:
        return []

    merged: List[SpeechSeg] = [out[0]]
    for s in out[1:]:
        prev = merged[-1]
        if s.start_ms - prev.end_ms <= settings.VAD_MERGE_GAP_MS:
            prev.end_ms = max(prev.end_ms, s.end_ms)
        else:
            merged.append(s)

    if len(merged) > settings.MAX_SPEECH_SEGMENTS:
        merged = merged[:settings.MAX_SPEECH_SEGMENTS]

    return merged


def transcribe_segments(
        wav_path: Path,
        speech: list[SpeechSeg],
        *,
        language: Optional[str],
        on_progress: Optional[ProgressFn]
) -> list[AsrSeg]:
    """


    :param wav_path:
    :param speech:
    :param language:
    :param on_progress:
    :return:
    """

    if not speech:
        return []

    audio_ndarray = _read_wav_mono_16k(wav_path)
    model = _load_asr_model()

    out: list[AsrSeg] = []
    for idx, seg in enumerate(speech):
        s0 = int(seg.start_ms * settings.TARGET_SR / 1000)
        s1 = int(seg.end_ms * settings.TARGET_SR / 1000)
        s0 = max(0, min(len(audio_ndarray), s0))
        s1 = max(0, min(len(audio_ndarray), s1))
        if s1 <= s0:
            continue

        clip = audio_ndarray[s0:s1]

        segments, info = model.transcribe(
            clip,
            language,
            vad_filter=False,
            beam_size=1,
            condition_on_previous_text=False
        )

        pct = 20 + int(60 * (idx + 1) / max(1, len(speech)))
        _prog(on_progress, pct, f"asr {idx + 1}/{len(speech)}")

        for s in segments:
            start_ms = seg.start_ms + int(float(s.start) * 1000)
            end_ms = seg.start_ms + int(float(s.end) * 1000)
            text = (s.text or "").strip()
            if not text:
                continue
            out.append(AsrSeg(start_ms=start_ms, end_ms=max(end_ms, start_ms + 1), text=text))

    out.sort(key=lambda t: (t.start_ms, t.end_ms))
    return out


def merge_asr_to_chunks(asr: list[AsrSeg]) -> list[AsrSeg]:
    """


    :param asr:
    :return:
    """

    if not asr:
        return []

    chunks: list[AsrSeg] = []
    cur_start = asr[0].start_ms
    cur_end = asr[0].end_ms
    buf: list[str] = [asr[0].text]

    def flush(force: bool = False) -> None:
        nonlocal cur_start, cur_end, buf
        txt = " ".join([b.strip() for b in buf if b.strip()]).strip()
        if not txt:
            buf = []
            return
        if len(txt) > settings.MAX_CHARS_PER_CHUNK:
            txt = txt[:settings.MAX_CHARS_PER_CHUNK]
        chunks.append(AsrSeg(start_ms=cur_start, end_ms=cur_end, text=txt))
        buf = []

    for s in asr[1:]:
        next_end = max(cur_end, s.end_ms)
        next_txt = (buf[-1] if buf else "")
        span = next_end - cur_start

        buf.append(s.text)
        cur_end = next_end

        span = cur_end - cur_start
        if span >= settings.MAX_CHUNK_MS:
            flush(force=True)
            cur_start = s.start_ms
            cur_end = s.end_ms
            buf = [s.text]
            continue

        if span >= settings.MIN_CHUNK_MS and _ends_with_punc(s.text):
            flush()
            cur_start = s.start_ms
            cur_end = s.end_ms
            buf = [s.text]

    if buf:
        flush(force=True)

    chunks.sort(key=lambda t: (t.start_ms, t.end_ms))
    return chunks


def run_audio_ingest_pipeline(
        *,
        audio_id: str,
        raw_path: Path,
        original_filename: str,
        visibility: str,
        language: Optional[str],
        wav_dir: Path,
        on_progress: Optional[ProgressFn] = None
) -> Dict[str, Any]:
    """


    :param audio_id:
    :param raw_path:
    :param original_filename:
    :param visibility:
    :param language:
    :param wav_dir:
    :param on_progress:
    :return:
    """
    if not raw_path.exists():
        raise FileNotFoundError(str(raw_path))

    _prog(on_progress, 1, "开始...")

    wav_dir.mkdir(parents=True, exist_ok=True)
    wav_path = wav_dir / f"{audio_id}.wav"

    _prog(on_progress, 5, "转码中（转成 WAV 文件）...")
    transcode_to_wav_16k_mono(raw_path, wav_path)

    duration_ms = ffprobe_duration_ms(wav_path)

    _prog(on_progress, 10, "音频 VAD 处理...")
    speech = detect_speech_segments(wav_path)

    _prog(on_progress, 15, "ASR 转义中...")
    asr = transcribe_segments(wav_path, speech, language=language, on_progress=on_progress)

    _prog(on_progress, 85, "正在将 ASR 转义后的文本分块")
    chunks = merge_asr_to_chunks(asr)

    _prog(on_progress, 88, f"分块数 = {len(chunks)}")

    rows: List[Dict[str, Any]] = []
    docs: List[Document] = []
    ids: List[str] = []

    for i, c in enumerate(chunks):
        seg_id = f"{audio_id}:{i}"
        start_ms = int(c.start_ms)
        end_ms = int(c.end_ms)
        text = (c.text or "").strip()

        rows.append({
            "audio_id": audio_id,
            "segment_idx": i,
            "segment_id": seg_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "text": text,
            "visibility": visibility,
        })

        meta = {
            "audio_id": audio_id,
            "segment_id": seg_id,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "visibility": visibility,
            "original_filename": original_filename,
        }

        docs.append(Document(page_content=text, metadata=meta))
        ids.append(seg_id)


    # 一次性写 MySQL
    _prog(on_progress, 90, "写入 MySql 数据库...")
    _db_replace_segments(audio_id, rows)

    # 一次性写 Chroma 向量库
    _prog(on_progress, 93, "写入 Chroma 数据库...")
    vs = get_audio_vs()
    _vs_add(vs, docs, ids)

    # 完成
    _prog(on_progress, 100, "任务已完成！！！")

    return {
        "audio_id": audio_id,
        "duration_ms": int(duration_ms),
        "segments": int(len(chunks)),
        "language": language,
        "wav_path": str(wav_path),
    }



