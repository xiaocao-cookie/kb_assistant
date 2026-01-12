from typing import Optional, Any

from app.db_ops.conn_pool import get_conn


def upsert_audio_document(
        *,
        audio_id: str,
        original_filename: str,
        stored_path: str,
        duration_ms: int,
        language: str | None,
        visibility: str,
        status: str,
        uploader_user_id: int | None,
        uploader_username: str | None,
        segment_count: int
) -> None:
    """
    更新并插入音频的相关信息

    :param audio_id: 音频 ID
    :param original_filename: 原文件名
    :param stored_path: 存储路径
    :param duration_ms: 音频的毫秒数
    :param language: 音频的语言
    :param visibility: 可见性
    :param status: 状态
    :param uploader_user_id: 上传者 ID
    :param uploader_username: 上传者名称
    :param segment_count: 分段的数量
    :return: 如果成功则返回 None， 否则引发异常
    """

    sql = """
          INSERT INTO audio_documents
          (audio_id, original_filename, stored_path, duration_ms, language, visibility, status,
           uploader_user_id, uploader_username, segment_count)
          VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY \
          UPDATE \
              original_filename= \
          VALUES (original_filename), stored_path= \
          VALUES (stored_path), duration_ms= \
          VALUES (duration_ms), language = \
          VALUES (language), visibility= \
          VALUES (visibility), status= \
          VALUES (status), uploader_user_id= \
          VALUES (uploader_user_id), uploader_username= \
          VALUES (uploader_username), segment_count= \
          VALUES (segment_count) \
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    audio_id, original_filename, stored_path, int(duration_ms), language,
                    visibility, status, uploader_user_id, uploader_username, int(segment_count)
                ),
            )


def replace_audio_segments(audio_id: str, segments: list[dict[str, Any]]) -> None:
    """
    使用 segments 提供的分段信息替换 audio_id 对应的分段数据

    :param audio_id: 音频 ID
    :param segments: 分段信息的列表
    :return: 如果成功，返回 None, 否则抛出异常
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audio_segments WHERE audio_id=%s", (audio_id,))
            if segments:
                cur.executemany(
                    "INSERT INTO audio_segments (audio_id, segment_idx, start_ms, end_ms, texts) VALUES (%s,%s,%s,%s,%s)",
                    [
                        (audio_id, int(s["segment_idx"]), int(s["start_ms"]), int(s["end_ms"]), s["text"])
                        for s in segments
                    ],
                )


def delete_audio_segments(audio_id: str) -> int:
    """
    根据 audio_id 删除 audio_segments 表中的所有分段

    :param audio_id: 音频 ID
    :return: 影响的数据库行数
    """
    sql = "DELETE FROM audio_segments WHERE audio_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (audio_id,))
            return int(cur.rowcount or 0)


def delete_audio_document(audio_id: str) -> int:
    """
    根据 audio_id 删除 audio_documents 中对应的音频信息

    :param audio_id: 音频 ID
    :return: 影响的数据库行数
    """
    sql = "DELETE FROM audio_documents WHERE audio_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (audio_id,))
            return int(cur.rowcount or 0)


def get_audio_document(audio_id: str) -> Optional[dict[str, Any]]:
    """
    通过 audio_id 在 audio_documents 表中查询对应音频的相关信息

    :param audio_id: 音频 ID
    :return: 对应的音频信息
    """

    sql = """SELECT audio_id, original_filename, stored_path, duration_ms, language, visibility, status, 
             uploader_user_id, uploader_username, segment_count, created_at, updated_at 
            FROM audio_documents WHERE audio_id=%s LIMIT 1
          """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (audio_id, ))
            return cur.fetchone()


def get_audio_segment(audio_id: str, segment_idx: int):
    """
    根据 audio_id 和 segment_idx 获取分段音频的信息

    :param audio_id: 音频 ID
    :param segment_idx: 音频的分段 ID
    :return: 音频信息
    """
    sql = """
          SELECT audio_id, segment_idx, start_ms, end_ms, texts 
          FROM audio_segments WHERE audio_id=%s AND segment_idx=%s LIMIT 1
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (audio_id, int(segment_idx)))
            return cur.fetchone()


def list_audio_segments(audio_id: str, *, limit: int = 2000) -> list[Any]:
    """
    根据 audio_id 查询 limit 条音频分段（segment）数据，并基于每个分段的 ID (segment_idx) 升序排序

    :param audio_id: 音频 ID
    :param limit: 限制的条数
    :return: 字典的列表
    """

    limit = max(1, min(int(limit), 5000))
    sql = """
             SELECT audio_id, segment_idx, start_ms, end_ms, text
             FROM audio_segments WHERE audio_id=%s 
             ORDER BY segment_idx ASC LIMIT %s
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (audio_id, limit),
            )

            rows = cur.fetchall() or []
            return [
                {
                    "audio_id": r[0],
                    "segment_idx": r[1],
                    "start_ms": r[2],
                    "end_ms": r[3],
                    "text": r[4],
                }
                for r in rows
            ]


def get_audio_transcript(audio_id: str, *, max_segments: int = 5000) -> str:
    """
    根据 audio_id 获取音频的转写信息

    :param audio_id: 音频 ID
    :param max_segments: 最多返回的音频分段的数量
    :return: 拼接后的完整转写文本
    """

    segs = list_audio_segments(audio_id, limit=max_segments)
    lines: list[str] = []
    for s in segs:
        lines.append(f"[{s['segment_idx']}] {s['text']}")
    return "\n".join(lines)


def get_audio_stats() -> dict[str, Any]:
    """
    获取 audio_documents 表的描述信息，包含总音频数量, visibility 和 status 的分组统计数量

    :return: 字典, 有以下三个键值对
        1. { 'by_visibility' : dict `键是 audio_documents 表中所有音频的 visibility, 值为对应的数量` }
        2. { 'by_status' : dict `键是 audio_documents 表中所有音频的 status，值为对应的数量` }
        3. { 'total' : int `总共有多少条` }

    """

    out = {"by_visibility": {}, "by_status": {}, "total": 0}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM audio_documents")
            out["total"] = int((cur.fetchone() or {}).get("cnt") or 0)

            cur.execute("SELECT visibility, COUNT(*) AS cnt FROM audio_documents GROUP BY visibility")
            for r in (cur.fetchall() or []):
                out["by_visibility"][str(r["visibility"])] = int(r["cnt"])

            cur.execute("SELECT status, COUNT(*) AS cnt FROM audio_documents GROUP BY status")
            for r in (cur.fetchall() or []):
                out["by_status"][str(r["status"])] = int(r["cnt"])

    return out


def list_audio_documents(
        *,
        q: str | None = None,
        visibility: str | None = None,
        status: str | None = None,
        uploader_user_id: int | None = None,
        page: int = 1,
        page_size: int = 20
) -> tuple[int, list[Any]]:
    """
    列出音频的文档信息，支持分页查询

    :param q: 查询键
    :param visibility: 音频可见性
    :param status: 音频的状态
    :param uploader_user_id: 上传者 ID
    :param page: 页数，第几页
    :param page_size: 每页容纳几条数据
    :return: 音频的总条数 和 每个分页的音频信息
    """

    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    offset = (page - 1) * page_size

    where = []
    params: list[Any] = []

    if q:
        qq = f"%{q.strip()}%"
        where.append("(audio_id LIKE %s OR original_filename LIKE %s OR uploader_username LIKE %s)")
        params.extend([qq, qq, qq])

    if visibility:
        v = visibility.strip().lower()
        where.append("visibility=%s")
        params.append(v)

    if status:
        s = status.strip().lower()
        where.append("status=%s")
        params.append(s)

    if uploader_user_id is not None:
        where.append("uploader_user_id=%s")
        params.append(int(uploader_user_id))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cnt_sql = f"SELECT COUNT(*) AS cnt FROM audio_documents {where_sql}"
    list_sql = f"""
                SELECT audio_id, original_filename, stored_path, duration_ms, language, visibility, status, 
                        uploader_user_id, uploader_username, segment_count, created_at, updated_at 
                FROM audio_documents {where_sql} 
                ORDER BY updated_at DESC, created_at DESC 
                LIMIT %s OFFSET %s
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(cnt_sql, tuple(params))
            total = int((cur.fetchone() or {}).get("cnt") or 0)

            cur.execute(list_sql, tuple(params + [page_size, offset]))
            items = cur.fetchall() or []
    return total, items


def update_audio_status(audio_id: str, status: str) -> None:
    """
    根据 audio_id 更新对应音频的 status

    :param audio_id: 音频 ID
    :param status: 音频的状态
    :return: 如果更新成功，返回 None, 否则引发异常
    """

    sql = "UPDATE audio_documents SET status=%s WHERE audio_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (status, audio_id))


def update_audio_indexed(
        audio_id: str,
        duration_ms: int,
        language: str | None,
        segment_count: int,
        status: str
) -> None:
    """
    根据 audio_id 更新对应音频的 duration_ms, language, segment_count 和 status

    :param audio_id: 音频 ID
    :param duration_ms: 音频的时长（毫秒）
    :param language: 音频的语言
    :param segment_count: 分段的个数
    :param status: 音频的状态
    :return: 如果更新成功，返回 None, 否则引发异常
    """

    sql = "UPDATE audio_documents SET duration_ms=%s, language=%s, segment_count=%s, status=%s WHERE audio_id=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                int(duration_ms),
                language,
                int(segment_count),
                status,
                audio_id
            ))


def update_audio_visibility(audio_id: str, visibility: str) -> None:
    """
    根据 audio_id 并使用 visibility 修改对应音频的可见性

    :param audio_id: 音频 ID
    :param visibility: 音频的可见性
    """
    sql = "UPDATE audio_documents SET visibility=%s WHERE audio_id=%s"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (visibility, audio_id))


def is_audio_running(audio_id: str) -> bool:
    """
    判断 audio_id 对应的音频是否在 queued 或 running 状态

    :param audio_id: 音频 ID
    :return: 如果在 queued 和 running 状态，返回 True，否则返回 False
    """

    sql = "SELECT status FROM audio_documents WHERE audio_id=%s LIMIT 1"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (audio_id,))
            row = cur.fetchone()
            return bool(row and row.get("status") in ("queued", "running"))