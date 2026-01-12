from functools import lru_cache

import chromadb

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> chromadb.ClientAPI:
    """ 获取 chromadb 的客户端实例 """
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


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