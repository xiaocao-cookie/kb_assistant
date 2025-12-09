import uvicorn
from fastapi import FastAPI, UploadFile, Form, HTTPException, File
from pydantic import BaseModel
from app.config import settings
from app.deps import get_vs
from app.router_graph import router_graph
from typing import Optional
from pathlib import Path
import time
import uuid
from app.ingestion.loader import load_single_file, split_with_visibility, load_docs, split_docs, batch_chunks
import chromadb
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="Enterprise KB Assistant")


# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 或者指定你的前端地址 ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DOCS_DIR = Path("../data/docs")
DATA_DOCS_DIR.mkdir(parents=True, exist_ok=True)            # 若不存在 → 自动递归创建所有目录
SESSIONS: dict[str, dict] = {}

class ChatReq(BaseModel):
    text: str
    user_role: str = "public"
    requester: str = "anonymous"
    mode: Optional[str] = None
    session_id: Optional[str] = None

class ChatResp(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResp)
def chat(req: ChatReq):
    """
    聊天接口，底层使用 langgraph

    :param req: 用户输入的问题
    :return: 大模型（使用RAG） 给出的回答
    """
    payload = req.model_dump()
    sid = payload.get("session_id")

    if sid and sid in SESSIONS:
        prev = SESSIONS[sid]
        merged = {**prev, **payload}
        merged["text"] = payload.get("text")
        payload = merged

    out = router_graph.invoke(payload)

    if sid:
        SESSIONS[sid] = {**payload, **out}

    return {"answer": out["answer"]}

@app.post("/ingest")
async def ingest(file: UploadFile = File(...),
                 visibility: str = Form("public"),
                 doc_id: Optional[str] = Form(None)):
    """
    将语料库上传到 chromadb/chroma 的某个 collection 中

    具体步骤如下：
    1. 上传一个文件，并将其保存到磁盘
    2. 将其切块，并给每个切块（Document对象）都增加上 visibility 和 doc_id 的元数据信息
    3. 最后添加到 chroma 数据库中

    :param file: 上传的文件
    :param visibility: 文件的可见性属性
    :param doc_id: 文件 id
    :return: 保存的路径，可见性，文件id和分块长度
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="空文件")

    visibility = (visibility or "public").strip().lower()

    suffix = Path(file.filename).suffix
    safe_name = f"{int(time.time())}_{uuid.uuid4().hex}{suffix}"
    save_path = DATA_DOCS_DIR / safe_name

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")
    save_path.write_bytes(content)

    docs = load_single_file(save_path)                                                  # 切块
    if not docs:
        raise HTTPException(status_code=400, detail="文件类型不支持或空文件")

    chunks = split_with_visibility(docs, visibility=visibility, doc_id=doc_id)          # 每一块带上可见性和文档id

    vs = get_vs()
    for chunks in batch_chunks(docs, 64):
        vs.add_documents(chunks)                                                            # 存到 chromadb 中

    return {
        "saved_as": str(save_path),
        "visibility": visibility,
        "doc_id": doc_id,
        "chunks": len(chunks)
    }


@app.post("/reindex")
def reindex(visibility_default: str = Form("public")):
    """
    带上默认的可见性信息，全量重建语料库

    :param visibility_default: 默认的可见性
    :return: 文件长度，切块长度和默认可见性的信息
    """
    visibility_default = (visibility_default or "public").strip().lower()

    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    try:
        client.delete_collection(settings.collection_name)
    except Exception:
        print(f"e:{Exception.__name__}")

    client.get_or_create_collection(settings.collection_name)

    vs = get_vs()
    raw_docs = load_docs(str(DATA_DOCS_DIR))
    if not raw_docs:
        return {"chunks": 0, "docs": 0, "messages": "在data/docs下没找到任何文件"}

    chunks = split_docs(raw_docs)
    for c in chunks:
        c.metadata = dict(c.metadata or {})
        c.metadata.setdefault("visibility", visibility_default)

    vs.add_documents(chunks)

    return {"docs": len(raw_docs), "chunks": len(chunks), "visibility_default": visibility_default}

@app.get("/")
def home():
    """ 主页面 """
    return {"success": "success"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8002, reload=True)