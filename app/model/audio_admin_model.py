from typing import Optional, List, Dict
from datetime import datetime

from pydantic import BaseModel, Field

class AudioDocItem(BaseModel):
    """ 音频文档的每一项，对应 MySql 中的 audio_documents 表"""
    audio_id: str
    original_filename: str
    stored_path: str
    duration_ms: int = 0
    language: Optional[str] = None
    visibility: str
    status: str
    uploader_user_id: Optional[int] = None
    uploader_username: Optional[str] = None
    segment_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AudioDocListResp(BaseModel):
    """ 查询音频文档返回的响应体 """
    total: int
    page: int
    page_size: int
    items: List[AudioDocItem]


class AudioSegmentItem(BaseModel):
    """ 音频的分段信息 """
    audio_id: str
    segment_idx: int
    start_ms: int
    end_ms: int
    text: str


class AudioSegmentsResp(BaseModel):
    """ 音频分段信息的响应体 """
    audio_id: str
    items: List[AudioSegmentItem]


class AudioTranscriptResp(BaseModel):
    """ 音频转写的响应体 """
    audio_id: str
    transcript: str


class AudioStatsResp(BaseModel):
    """ 音频状态的响应体 """
    by_visibility: Dict[str, int]
    by_status: Dict[str, int]
    total: int


class UpdateVisibilityReq(BaseModel):
    """ 更新音频可见性的请求体 """
    visibility: str = Field(..., description="public/internal")


class UpdateVisibilityResp(BaseModel):
    """ 更新音频可见性的响应体 """
    audio_id: str
    visibility: str
    vectors_updated: int


class BulkDeleteReq(BaseModel):
    """ 批量删除音频的请求体 """
    audio_ids: list[str]
    delete_files: bool = False


class BulkDeleteResp(BaseModel):
    """ 批量删除音频的响应体 """
    deleted: List[str]
    missing: List[str]
    vectors_deleted: Dict[str, int]
    files_deleted: List[str]


class BulkReindexReq(BaseModel):
    """ 批量重建音频的请求体 """
    audio_ids: List[str]


class ReindexItem(BaseModel):
    """ 重建音频索引的每一项的模型 """
    audio_id: str
    job_id: str
    celery_task_id: str
    status_url: str


class BulkReindexResp(BaseModel):
    """ 批量重建音频的响应体 """
    submitted: List[ReindexItem]
    skipped_running: List[str]
    missing: List[str]


class ResetAudioCollectionResp(BaseModel):
    """ 重置音频存储的 collection 的响应体 """
    ok: bool
    collection: str
