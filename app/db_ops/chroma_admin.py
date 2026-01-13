from functools import lru_cache
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> chromadb.ClientAPI:
    """ 获取 chromadb 的客户端实例 """
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def delete_collection(*, collection_name: str = settings.collection_name) -> None:
    """
    删除 chromadb 中名为 collection_name 的 collection

    :param collection_name: Collection 的名称，默认 knowledge_base
    """
    client = get_client()
    client.delete_collection(collection_name)


def delete_vectors_by_where(
        *,
        collection: Collection,
        where: dict[str, Any]
) -> int:
    """
    根据 where 条件删除 collection 中已嵌入的向量

    :param collection: Collection 的名称
    :param where: 删除的条件
    :return: 删除的向量数量
    """

    try:
        got = collection.get(where=where)
        ids = got.get("ids") or []
        if ids:
            collection.delete(ids=ids)
        return int(len(ids))
    except Exception:
        return 0


def get_collection(collection_name: str = settings.collection_name):
    """
    获取/创建 chromadb 中名为 collection_name 的 collection

    :param collection_name: Collection 的名称，默认 knowledge_base
    :return: Collection
    """
    client = get_client()
    return client.get_or_create_collection(collection_name)


def reset_collection(*, collection_name: str = settings.collection_name):
    """
    重置 chromadb 中名为 collection_name 的 collection

    :param collection_name: Collection 的名称，默认 knowledge_base
    :return: Collection
    """
    client = get_client()
    try:
        client.delete_collection(collection_name)
    except Exception:
        raise RuntimeError(f"删除 {collection_name} 时失败")

    return get_collection(collection_name)