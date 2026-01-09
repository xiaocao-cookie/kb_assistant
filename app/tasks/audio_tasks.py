from pathlib import Path

from celery.exceptions import Ignore

from app.celery_app import celery_app
from app.db_ops.audio_job_sql import (
    get_job_flags,
    update_job,
    is_cancel_requested,
    mark_cancelled
)
from app.db_ops.audio_sql import (
    update_audio_status,
    get_audio_document,
    update_audio_indexed
)
from app.constants.audio_job import AudioJobStatus
from app.rag.chroma_admin import delete_by_audio_id
from app.pipeline import run_audio_ingest_pipeline
from app.config import settings


def _check_cancel(job_id: str):
    """
    检查 job_id 对应的任务是否有客户的取消请求，用来设置 celery 执行任务时的检查点

    :param job_id: 任务 ID
    """

    if is_cancel_requested(job_id):
        mark_cancelled(job_id)
        raise Ignore()

# todo: 补充文档
@celery_app.task(
    bind=True,                                  # 把此函数变为类的实例方法，第一个参数必须是 ⚠️self!!!
    autoretry_for=(IOError, ),                  # todo: 异常优化
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3}
)
def audio_ingest_task(self, job_id: str, audio_id: str):
    """
    根据调用 /audio/ingest 生成的 job_id 和 audio_id 异步的进行音频上传的任务，音频信息会同步到 chroma 和 MySql 中

    :param self: 类实例方法的第一个参数，与装饰器中的 bind=True 联用
    :param job_id: 任务 ID
    :param audio_id: 音频 ID
    """

    flags = get_job_flags(job_id)
    old_path = flags.get("old_stored_path")
    delete_old_file = bool(int(flags.get("delete_old_file", 0) or 0))

    update_job(job_id, status=AudioJobStatus.RUNNING, progress=1, message="任务开始")
    update_audio_status(audio_id, status=AudioJobStatus.RUNNING)

    _check_cancel(job_id)

    doc = get_audio_document(audio_id)
    if not doc:
        raise RuntimeError(f"音频ID：{audio_id} 对应的文档未找到")

    raw_path = Path(doc["stored_path"])
    if not raw_path.exists():
        raise RuntimeError("存储的音频路径不存在")

    update_job(job_id, progress=5, message="清除旧的向量存储")
    delete_by_audio_id(audio_id)

    _check_cancel(job_id)

    update_job(job_id, progress=10, message="新的音频正在嵌入到数据库中")
    result = run_audio_ingest_pipeline(
        audio_id=audio_id,
        raw_path=raw_path,
        original_filename=doc["original_filename"],
        visibility=doc["visibility"],
        language=doc.get("language"),
        wav_dir=Path(settings.AUDIO_WAV_DIR)
    )

    _check_cancel(job_id)

    update_audio_indexed(
        audio_id=audio_id,
        duration_ms=int(result["duration_ms"]),
        language=result.get("language"),
        segment_count=int(result["segments"]),
        status="indexed"
    )

    update_job(job_id, status=AudioJobStatus.SUCCEEDED, progress=100, message=f"嵌入了 {result['segments']} 个 segments")

    if delete_old_file and old_path and old_path != str(raw_path):
        try:
            p = Path(str(old_path))
            if p.exists() and p.is_file():
                p.unlink()
        except Exception:
            print(f"e: {Exception.__name__}")

    return result


