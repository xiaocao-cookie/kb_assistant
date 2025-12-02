from app.rag.vectorstore import get_vectorstore
from app.config import settings
from langchain_community.embeddings import ZhipuAIEmbeddings
from zhipuai import ZhipuAI
from langchain_openai import ChatOpenAI

# response = client.chat.completions.create(
#     model=settings.model_name,
#     messages=[{"role": "user", "content": "你是谁？"}],  # type: ignore[arg-type]
#     temperature=0
# )
# return response.choices[0].message.content


def get_llm():
    """
    获取大语言模型 ———— 使用的是deepseek
    """
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.base_url,
        model=settings.model_name,
        streaming=True,
        temperature=0
    )


def get_embeddings():
    """
    获取嵌入式模型
    """
    return ZhipuAIEmbeddings(
        client=ZhipuAI(api_key=settings.zhipu_api_key,
                       base_url="https://open.bigmodel.cn/api/paas/v4/embeddings"),
        model="embedding-3",
        api_key=settings.zhipu_api_key
    )


def get_vs():
    """
    获取向量存储
    """
    return get_vectorstore(get_embeddings())


if __name__ == "__main__":
    print(get_embeddings())