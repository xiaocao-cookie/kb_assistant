from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AudioJobResp(BaseModel):
    """ 音频任务响应模型 """
    job_id: str
    audio_id: str
    celery_task_id: Optional[str] = None

    status: str                 # queued/running/succeeded/failed/cancelled
    progress: int = 0
    message: Optional[str] = None

    cancel_requested: bool = False
    overwrite: bool = False
    delete_old_file: bool = False
    old_stored_path: Optional[str] = None
    cancelled_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

