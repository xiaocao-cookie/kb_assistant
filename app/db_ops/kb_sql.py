from typing import Optional, Any

from app.db_ops.conn_pool import get_conn

# todo： 优化文档
def upsert_kb_document(
        *,
        doc_id: str,
        original_filename: str,
        stored_path: str,
        visibility: str,
        uploader_user_id: int | None,
        uploader_username: str | None,
        chunk_count: int = 0
) -> None:
    """
    插入/更新一个知识库文档

    :param doc_id: 文档 ID
    :param original_filename: 原文件名
    :param stored_path: 存储路径
    :param visibility: 可见性
    :param uploader_user_id: 上传者 ID
    :param uploader_username: 上传着名称
    :param chunk_count: 分块数量
    :return: 知识库文档
    """
    sql = """
    INSERT INTO kb_documents
        (doc_id, original_filename, stored_path, visibility, uploader_user_id, uploader_username, chunk_count)
    VALUES
        (%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
        original_filename = VALUES(original_filename),
        stored_path = VALUES(stored_path),
        visibility = VALUES(visibility),
        uploader_user_id = VALUES(uploader_user_id),
        uploader_username = VALUES(uploader_username),
        chunk_count = VALUES(chunk_count),
        is_deleted = 0
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    doc_id,
                    original_filename,
                    stored_path,
                    visibility,
                    uploader_user_id,
                    uploader_username,
                    int(chunk_count or 0),
                ),
            )



def list_kb_documents(
        *,
        limit: int = 50,
        offset: int = 0,
        visibility: str | None = None
) -> list[dict[str, Any]]:
    """
    根据 visibility(可选) 列出 kb_documents 表中的前 limit 条数据，偏移量默认为 0
    默认的排序方式： 更新时间降序排列
    默认每条记录的状态： is_deleted = 0

    :param limit: 数据的条数
    :param offset: 偏移量
    :param visibility: 文件的可见性
    :return: 查询出的文档数据
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    sql = """
    SELECT doc_id, original_filename, stored_path, visibility, uploader_user_id, 
           uploader_username, chunk_count, created_at, updated_at 
    FROM kb_documents WHERE is_deleted=0 
    """

    args: list[Any] = []
    if visibility:
        sql += "AND visibility = %s "
        args.append(visibility)
    sql += "ORDER BY updated_at DESC LIMIT %s OFFSET %s"
    args.extend([limit, offset])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(args))
            return cur.fetchall()


def get_kb_document(doc_id: str) -> Optional[dict[str, Any]]:
    """
    获取 doc_id 对应的知识库文档

    :param doc_id: 文档 ID
    :return: 知识库文档
    """
    sql = """
    SELECT doc_id, original_filename, stored_path, visibility, uploader_user_id, uploader_username, chunk_count, created_at, updated_at
    FROM kb_documents WHERE doc_id=%s AND is_deleted=0 LIMIT 1
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (doc_id,))
            return cur.fetchone()


def update_kb_document_visibility(doc_id: str, visibility: str) -> bool:
    """
    根据 doc_id 更新对应文档的可见性(visibility)

    :param doc_id: 文档 ID
    :param visibility: 可见性
    :return: 是否更新成功
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kb_documents SET visibility=%s WHERE doc_id=%s AND is_deleted=0",
                (visibility, doc_id),
            )
            return cur.rowcount > 0


def update_kb_document_chunk_count(doc_id: str, chunk_count: int) -> bool:
    """
    根据 doc_id 并将对应文档的分块数量更新为 chunk_count

    :param doc_id: 文档 ID
    :param chunk_count: 分块数量
    :return: 是否更新成功
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kb_documents SET chunk_count=%s WHERE doc_id=%s AND is_deleted=0",
                (int(chunk_count or 0), doc_id),
            )
            return cur.rowcount > 0


def soft_delete_kb_document(doc_id: str) -> bool:
    """
    将 doc_id 对应的文档进行逻辑删除,即 is_deleted = 1
    :param doc_id: 文档 ID
    :return: 是否进行了逻辑删除
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE kb_documents SET is_deleted=1 WHERE doc_id=%s AND is_deleted=0",
                (doc_id,),
            )
            return cur.rowcount > 0
