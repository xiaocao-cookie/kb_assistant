from typing import Any

import chromadb

from app.config import settings


def get_collection(collection_name: str = settings.collection_name):
    """
    获取/创建 chromadb 中名为 collection_name 的 collection

    :return: Collection
    """
    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return client.get_or_create_collection(collection_name)