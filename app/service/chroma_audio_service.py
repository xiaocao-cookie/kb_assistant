from typing import Iterable, Any

from app.config import settings
from app.db_ops.chroma_admin import get_collection, delete_vectors_by_where


def delete_by_audio_id(audio_id: str) -> int:
    """
    通过 audio_id 从 ChromaDB 中删除对应的音频嵌入向量

    :param audio_id: 音频 ID
    :return: 删除的向量的嵌入数量
    """

    col = get_collection(settings.audio_collection_name)
    where = {"audio_id": audio_id}
    return delete_vectors_by_where(collection=col, where=where)


def delete_many_audio_ids(audio_ids: Iterable[str]) -> dict[str, int]:
    """
    根据 audio_ids 中的音频 ID 批量删除向量数据库中的音频向量

    :param audio_ids: audio_id 的可迭代对象
    :return: 字典，每一项的键是 audio_id, 值是对应删除的向量数量
    """
    out: dict[str, int] = {}
    for aid in audio_ids:
        aid = (aid or "").strip()
        if not aid:
            continue
        try:
            out[aid] = int(delete_by_audio_id(aid))
        except Exception:
            out[aid] = 0
    return out


def get_ids_and_metadatas_by_audio_id(audio_id: str) -> tuple[list[str], list[dict[str, Any]]]:
    """
    根据 audio_id 获取 chroma 数据库中对应向量的元数据

    :param audio_id: 音频 ID
    :return: 包含两个列表的元组
            列表 1： 每个嵌入的音频向量的 ids
            列表 2： 每个嵌入的音频向量的 metadata
    """
    col = get_collection(settings.audio_collection_name)
    got = col.get(where={"audio_id": audio_id}, include=["metadatas"])
    ids = got.get("ids") or []
    metas = got.get("metadatas") or []
    return list(ids), list(metas)


def update_visibility_by_audio_id(audio_id: str, visibility: str) -> int:
    """
    根据 audio_id 更新音频的可见性

    :param audio_id: 音频 ID
    :param visibility: 音频的可见性
    :return: 影响的数据库行数，即更新的向量数量
    """

    col = get_collection(settings.audio_collection_name)

    ids, metas = get_ids_and_metadatas_by_audio_id(audio_id)
    if not ids:
        return 0

    new_metas: list[dict[str, Any]] = []
    for m in metas:
        mm = dict(m or {})
        mm["visibility"] = visibility
        new_metas.append(mm)

    col.update(ids=ids, metadatas=new_metas)
    return len(ids)
