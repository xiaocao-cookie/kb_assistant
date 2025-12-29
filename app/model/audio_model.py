from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

# todo: 文档完善
class AudioIngestResp(BaseModel):
    """ 音频嵌入的请求体 """
    audio_id: str
    stored_as: str
    duration_ms: int
    language: Optional[str] = None
    visibility: str
    segments: int


class AudioDocDetail(BaseModel):
    """  """
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
    """  """
    audio_id: str
    segment_id: str
    start_ms: int
    end_ms: int
    texts: str
    score: Optional[float] = None


class AudioSearchResp(BaseModel):
    """ 音频搜索的响应体 """
    q: str
    k: int
    allowed_visibilities: List[str]
    hits: List[AudioSearchHit]