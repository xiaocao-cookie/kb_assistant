import chromadb
from app.config import settings
from langchain_chroma import Chroma


def get_vectorstore(embeddings):
    """
    从嵌入层中获取向量存储
    :param embeddings:
    :return: 一个chroma对象，用于管理和查询嵌入向量
    """
    # 连接时请先启动chroma
    # sudo docker run -d \
    #   --name chroma \
    #   -p 8000:8000 \
    #   -e IS_PERSISTENT=TRUE \
    #   -e PERSIST_DIRECTORY=/chroma/chroma \
    #   -v /home/supercao/PycharmProjects/kb_assistant/data/chroma:/chroma/chroma \
    #   chromadb/chroma
    client = chromadb.HttpClient(
        host=settings.chroma_host,
        port=settings.chroma_port
    )        # 连接到 chorma 服务

    return Chroma(
        client=client,
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory="/chroma/chroma"
    )