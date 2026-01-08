from dotenv import load_dotenv
from pydantic import BaseModel
import os
from pathlib import Path

load_dotenv()

class Setting(BaseModel):
    """
    基本的配置：
        包含
        apikey/调用的模型/chroma数据库的目录/chroma启动的主机和端口/chroma数据库的集合名称/
        块大小和块折叠...
    """
    base_url: str = 'https://api.deepseek.com/v1'
    openai_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    zhipu_api_key: str = os.getenv("ZHIPUAI_API_KEY", "")
    model_name: str = os.getenv("MODEL_NAME", "deepseek-chat")

    # ================= chroma数据库 =========================
    chroma_dir: str = os.getenv("CHROMA_DIR", "./data/chroma")
    chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
    chroma_port: int = int(os.getenv("CHROMA_PORT", "8000"))

    # ================= MySql 数据库 =========================
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "cao")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "123456")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "kb_assistant")

    # ================= 知识库处理配置 =========================
    collection_name: str = os.getenv("COLLECTION_NAME", "knowledge_base")
    DATA_DOCS_DIR: Path = Path("/home/supercao/PycharmProjects/kb_assistant/data/docs")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "120"))


    # ================= 音频处理配置 =========================
    audio_collection_name: str = os.getenv("AUDIO_COLLECTION_NAME", "audio_base")

    # ffmpeg 用于转码/处理
    ffmpeg_cmd: str = os.getenv("FFMPEG_CMD", "/home/supercao/Downloads/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg")
    # ffprobe 用于查看媒体的信息
    ffprobe_cmd: str = os.getenv("FFPROBE_CMD", "/home/supercao/Downloads/ffmpeg-master-latest-linux64-gpl/bin/ffprobe")

    TARGET_SR: int = int(os.getenv("AUDIO_SR", "16000"))                     # Sample Rate 采样率
    TARGET_CH: int = int(os.getenv("AUDIO_CH", "1"))                         # Channel 通道数

    VAD_MODE: int = int(os.getenv("VAD_MODE", "2"))
    VAD_FRAME_MS: int = int(os.getenv("VAD_FRAME_MS", "30"))                 # 每帧音频长度（ms）
    VAD_PADDING_MS: int = int(os.getenv("VAD_PADDING_MS", "300"))            # 每段语音前后保留的额外时间（ms）
    VAD_MIN_SPEECH_MS: int = int(os.getenv("VAD_MIN_SPEECH_MS", "500"))      # 被认为是语音的最短时间（ms）
    VAD_MERGE_GAP_MS: int = int(os.getenv("VAD_MERGE_GAP_MS", "250"))        # 相邻语音段合并的最大间隔（ms）

    ASR_MODEL: str = os.getenv("ASR_MODEL", "base")
    ASR_DEVICE: str = os.getenv("ASR_DEVICE", "cpu")
    ASR_COMPUTE_TYPE: str = os.getenv("ASR_COMPUTE_TYPE", "int8")

    MAX_CHUNK_MS: int = int(os.getenv("AUDIO_MAX_CHUNK_MS", "25000"))
    MIN_CHUNK_MS: int = int(os.getenv("AUDIO_MIN_CHUNK_MS", "6000"))
    MAX_CHARS_PER_CHUNK: int = int(os.getenv("AUDIO_MAX_CHARS_PER_CHUNK", "900"))

    PUNCT_END: set = set("。.!?！？；;")                                     # 常见标点符号

    MAX_SPEECH_SEGMENTS: int = int(os.getenv("AUDIO_MAX_SPEECH_SEGMENTS", "2000"))

    AUDIO_DIR: Path = Path("/home/supercao/PycharmProjects/kb_assistant/app/data/audio")  # todo: 作 OS 对象存储
    AUDIO_WAV_DIR: Path = Path("/home/supercao/PycharmProjects/kb_assistant/app/data/audio_wav")
    CLIP_DIR: Path = Path("/home/supercao/PycharmProjects/kb_assistant/app/data/audio_clips")  # todo： 作对象存储

    # ================= 异步调度 =========================
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "amqp://cao:123456@127.0.0.1:5672/%2F")
    celery_audio_queue: str = "audio"

settings = Setting()