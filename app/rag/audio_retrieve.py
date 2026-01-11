from app.deps import get_audio_vs

#  todo: 函数的用法待优化
def audio_similarity_search(query: str, *, k: int = 6, where: dict | None = None):
    """
    搜索与 query 最近的 k 个向量(文档)

    :param query: 查询键
    :param k: 最邻近的 k 个
    :param where: 元数据的过滤条件
    :return: 最近的文档和其距离的列表
    """
    vs = get_audio_vs()
    docs_scores = vs.similarity_search_with_score(query, k=k, filter=where)

    return docs_scores