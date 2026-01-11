from app.config import settings
from app.utils.chroma_admin import get_collection


def delete_by_audio_id(audio_id: str) -> int:
    """
    通过 audio_id 从 ChromaDB 中删除对应的音频嵌入向量

    :param audio_id: 音频 ID
    :return: 删除的向量的嵌入数量
    """

    col = get_collection(settings.audio_collection_name)
    try:
        before = col.count()
        col.delete(where={"audio_id": audio_id})
        after = col.count()
        return max(0, int(before - after))
    except Exception:
        got = col.get(where={"audio_id": audio_id})
        ids = got.get("ids") or []
        if ids:
            col.delete(ids=ids)
        return len(ids)