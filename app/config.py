from dotenv import load_dotenv
from pydantic import BaseModel
import os

load_dotenv()

class Setting(BaseModel):
    """
    基本的配置：
        包含
        apikey/调用的模型/chroma数据库的目录/chroma启动的主机和端口/chroma数据库的集合名称/
        块大小和块折叠
    """
    base_url: str = 'https://api.deepseek.com/v1'
    openai_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    zhipu_api_key: str = os.getenv("ZHIPUAI_API_KEY", "")
    model_name: str = os.getenv("MODEL_NAME", "deepseek-chat")
    chroma_dir: str = os.getenv("CHROMA_DIR", "./data/chroma")
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))
    collection_name: str = os.getenv("COLLECTION_NAME", "knowledge_base")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))

settings = Setting()