from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AudioIngestResp(BaseModel):
    """ 音频嵌入的响应体 """
    audio_id: str
    stored_as: str
    duration_ms: int
    language: Optional[str] = None
    visibility: str
    segments: int


class AudioDocDetail(BaseModel):
    """ 对应于 MySQL 数据库中的 audio_documents 表 """
    audio_id: str
    original_filename: str
    stored_path: str
    duration_ms: int
    language: Optional[str] = None
    visibility: str
    status: str
    segment_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AudioSearchHit(BaseModel):
    """ 一个音频搜索中单个分段的信息 """
    audio_id: str
    segment_id: str
    start_ms: int
    end_ms: int
    texts: str
    score: Optional[float] = None
    clip_url: Optional[str] = None              # 可供用户下载的链接


class AudioSearchResp(BaseModel):
    """ 音频搜索的响应体 """
    q: str
    k: int
    allowed_visibilities: list[str]
    hits: list[AudioSearchHit]


class AudioIngestAsyncResp(BaseModel):
    """ 音频入库的异步响应 """
    job_id: str
    audio_id: str
    stored_as: str
    visibility: str
    celery_task_id: str
    status_url: str