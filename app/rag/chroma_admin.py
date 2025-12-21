from typing import Any

import chromadb

from app.config import settings


def get_collection():
    """

    :return:
    """
    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return client.get_or_create_collection(settings.collection_name)


def delete_by_doc_id(doc_id: str) -> int:
    """

    :param doc_id:
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

    :param doc_id:
    :return:
    """
    col = get_collection()
    got = col.get(where={"doc_id": doc_id}, include=["metadatas"])
    ids = got.get("ids") or []
    metadatas = got.get("metadatas") or []
    return list(ids), list(metadatas)


def count_by_doc_id(doc_id: str) -> int:
    """

    :param doc_id:
    :return:
    """
    ids, _ = get_ids_and_metadatas_by_doc_id(doc_id)
    return len(ids)


def update_visibility_by_doc_id(doc_id: str, visibility: str) -> int:
    """

    :param doc_id:
    :param visibility:
    :return:
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