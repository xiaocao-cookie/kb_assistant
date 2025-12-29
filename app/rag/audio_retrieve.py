from app.deps import get_vs

def audio_similarity_search_for_user(query: str, k: int = 6):
    """

    :param query:
    :param k:
    :return:
    """
    vs = get_vs()       # todo： 换 collection 存储
    # allowed = compute_allowed_kb_visibilities(user)
    docs = vs.similarity_search(query, k=k, filter={"visibility": 'public'})

    return docs, ['public']