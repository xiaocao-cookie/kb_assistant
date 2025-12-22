from typing import Any

import chromadb

from app.config import settings

# todo: 这个文件的文档需重新斟酌

def get_collection():
    """
    获取/创建 chroma 中的某个 collection
    :return: Collection
    """
    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return client.get_or_create_collection(settings.collection_name)


def delete_by_doc_id(doc_id: str) -> int:
    """
    通过 doc_id 删除对应的文档
    :param doc_id: 文件 ID
    :return:
    """
    col = get_collection()
    try:
        before = col.count()
        col.delete(where={"doc_id": doc_id})
        after = col.count()
        return max(0, int(before - after))
    except Exception:
        got = col.get(where={"doc_id": doc_id})
        ids = got.get("ids") or []
        if ids:
            col.delete(ids=ids)
        return len(ids)


def get_ids_and_metadatas_by_doc_id(doc_id: str) -> tuple[list[str], list[dict[str, Any]]]:
    """
    通过 doc_id 获取对应文档的 ids 和 元数据
    :param doc_id: 文档 ID
    :return: （ids的列表，元数据的列表）
    """
    col = get_collection()
    got = col.get(where={"doc_id": doc_id}, include=["metadatas"])
    ids = got.get("ids") or []
    metadatas = got.get("metadatas") or []
    return list(ids), list(metadatas)


def count_by_doc_id(doc_id: str) -> int:
    """
    通过 doc_id 计算文档数量
    :param doc_id: 文档 ID
    :return: 文档的数量
    """
    ids, _ = get_ids_and_metadatas_by_doc_id(doc_id)
    return len(ids)


def update_visibility_by_doc_id(doc_id: str, visibility: str) -> int:
    """
    通过 doc_id 和 visibility 更新文档的元数据
    :param doc_id: 文档 ID
    :param visibility: 文档的可见性
    :return: 影响的数据库行数
    """
    col = get_collection()
    ids, metadatas = get_ids_and_metadatas_by_doc_id(doc_id)
    if not ids:
        return 0
    new_metadatas: list[dict[str, Any]] = []
    for m in metadatas:
        meta_dict = dict(m or {})
        meta_dict["visibility"] = visibility
        new_metadatas.append(meta_dict)
    col.update(ids, new_metadatas)
    return len(ids)