import chromadb
from app.config import settings
from langchain_chroma import Chroma


def get_client():
    """  """
    return chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port
    )

def get_vectorstore(embeddings):
    """
    从嵌入层中获取向量存储
    :param embeddings:
    :return: 一个chroma对象，用于管理和查询嵌入向量
    """

    return Chroma(
        client=get_client(),
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory="/chroma/chroma"
    )


def get_audio_vectorstore(embeddings):
    return Chroma(
        client=get_client(),
        collection_name=settings.audio_collection_name,
        embedding_function=embeddings,
    )