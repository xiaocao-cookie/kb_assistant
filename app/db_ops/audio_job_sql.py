from typing import Any, Optional


from app.db_ops.conn_pool import get_conn


def create_job(
        job_id: str,
        audio_id: str,
        *,
        overwrite: bool = False,
        delete_old_file: bool = False,
        old_stored_path: str | None = None
) -> None:
    """
    向 audio_jobs 表中插入一条音频入库工作记录，状态默认设置为 queued(排队中)
    该记录中可以指定以下字段

    :param job_id: 音频入库的任务 ID
    :param audio_id: 要入库的音频 ID
    :param overwrite: 是否重写
    :param delete_old_file: 是否删除旧文件
    :param old_stored_path: 之前的存储路径
    :return: 若成功创建，返回 None,否则引发异常
    """

    sql = """INSERT 
             INTO audio_jobs (job_id, audio_id, status, progress, overwrite, delete_old_file, old_stored_path) 
             VALUES (%s,%s,'queued',0,%s,%s,%s)"""

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                job_id,
                audio_id,
                int(overwrite),
                int(delete_old_file),
                old_stored_path)
            )


def bind_task(job_id: str, celery_task_id: str) -> None:
    """
    根据 job_id 更新 celery_task_ids，即将音频入库的任务和 Celery 异步的任务一一对应

    :param job_id: 音频入库的任务 ID
    :param celery_task_id: Celery 的任务ID
    :return: 若成功，返回 None,否则引发异常
    """

    sql = "UPDATE audio_jobs SET celery_task_id=%s WHERE job_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (celery_task_id, job_id))


def update_job(
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None
) -> None:
    """
    根据 job_id 更新对应音频入库任务的 status, progress 和 message

    :param job_id: 任务 ID
    :param status: 任务状态
    :param progress: 任务执行的进度
    :param message: 任务说明
    :return:
    """

    fields = []
    args: list[Any] = []
    if status:
        fields.append("status=%s")
        args.append(status)
    if progress:
        fields.append("progress=%s")
        args.append(int(progress))
    if message:
        fields.append("message=%s")
        args.append(message)
    if not fields:
        return
    sql = f"UPDATE audio_jobs SET {', '.join(fields)} WHERE job_id = %s"
    args.append(job_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(args))


def get_job(job_id: str) -> Optional[dict]:
    """
    通过 job_id 获取对应的音频入库任务信息

    :param job_id: 任务 ID
    :return: 对应的任务信息
    """

    sql = """
          SELECT job_id, audio_id, celery_task_id, status, progress, message, cancel_requested, overwrite, 
                delete_old_file, old_stored_path, cancelled_at, created_at, updated_at 
          FROM audio_jobs 
          WHERE job_id=%s LIMIT 1
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id, ))
            return cur.fetchone()


def request_cancel(job_id: str) -> bool:
    """
    将 job_id 对应任务的 cancel_requested 字段设置为 1(确认)状态，并将 message 字段更新为 'cancel requested'

    :param job_id: 任务 ID
    :return: 请求取消字段是否成功更新，若成功，返回 True, 否则返回 False
    """

    sql = "UPDATE audio_jobs SET cancel_requested=1, message='cancel requested' WHERE job_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            return cur.rowcount > 0


def is_cancel_requested(job_id: str) -> bool:
    """
    查询 job_id 对应的任务是否处于请求取消状态

    :param job_id: 任务 ID
    :return: 若请求取消字段为 1，返回 True, 否则返回 False
    """

    sql = "SELECT cancel_requested FROM audio_jobs WHERE job_id=%s LIMIT 1"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            row = cur.fetchone()
            return bool(row and int(row.get("cancel_requested", 0)) == 1)


def mark_cancelled(job_id: str, message: str = "cancelled") -> None:
    """
    将 job_id 对应的音频入库任务标记为 cancelled 状态，并添加对应的 message 说明

    :param job_id: 工作ID
    :param message: 任务说明
    :return: 标记成功，返回 True,否则返回 False
    """

    sql = "UPDATE audio_jobs SET status='cancelled', progress=100, message=%s, cancelled_at=NOW() WHERE job_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (message, job_id),)


# todo： 明确文档
def get_job_flags(job_id: str) -> dict:
    """


    :param job_id: 音频入库任务的 ID
    :return: 对应任务的信息
    """

    sql = """SELECT overwrite, delete_old_file, old_stored_path, cancel_requested 
             FROM audio_jobs 
             WHERE job_id=%s LIMIT 1
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (job_id,))
            return cur.fetchone() or {}