from app.deps import get_audio_vs


def audio_similarity_search_for_user(query: str, k: int = 6):
    """
    搜索与 query 最近的 k 个向量(文档)

    :param query: 查询键
    :param k: 最邻近的 k 个
    :return: 文档和可见性
    """
    vs = get_audio_vs()
    docs = vs.similarity_search(query, k=k, filter={"visibility": 'public'})

    return docs, ['public']