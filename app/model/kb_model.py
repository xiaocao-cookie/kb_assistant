from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class KBDocListItem(BaseModel):
    """ 对应数据库中的 kb_documents 表"""
    doc_id: str
    original_filename: str
    stored_path: str
    visibility: str
    uploader_user_id: Optional[int] = None
    uploader_username: Optional[str] = None
    chunk_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KBDocDetail(KBDocListItem):
    """ 存储在chroma中该文档的块数 """
    chroma_chunk_count: int = 0


class KBDocVisibilityUpdateReq(BaseModel):
    """ 更新知识库文档的请求体 """
    visibility: str = Field(..., min_length=1)          # 必填字段


class KBDocReembedResp(BaseModel):
    """ 重新嵌入知识库文档的响应体 """
    doc_id: str
    deleted_chunks: int
    new_chunks: int
    visibility: str

