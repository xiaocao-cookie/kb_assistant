import uuid
from typing import Optional
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from app.router_graph import router_graph
from app.db_ops.redis_session import load_session, save_session
from app.api.auth_api import auth_router
from app.api.rbac_api import rbac_roles_router, rbac_users_router
from app.api.kb_api import kb_router
from app.api.audio_api import audio_router


app = FastAPI(title="Enterprise KB Assistant")
app.include_router(auth_router)
app.include_router(rbac_roles_router)
app.include_router(rbac_users_router)
app.include_router(kb_router)
app.include_router(audio_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 本地开发可以先全开，线上再收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DOCS_DIR = Path("../data/docs")
DATA_DOCS_DIR.mkdir(parents=True, exist_ok=True)            # 若不存在 → 自动递归创建所有目录

class ChatReq(BaseModel):
    text: str
    user_role: str = "public"
    requester: str = "anonymous"
    mode: Optional[str] = None
    session_id: Optional[str] = None

class ChatResp(BaseModel):
    answer: str
    session_id: Optional[str] = None
    active_route: Optional[str] = None


@app.post("/chat", response_model=ChatResp)
def chat(req: ChatReq):
    """
    聊天接口，底层使用 langgraph

    :param req: 用户输入的问题
    :return: 大模型（使用RAG）给出的回答
    """
    payload = req.model_dump()
    text = payload.get("text") or payload.get("question") or ""
    sid = payload.get("session_id") or f"sid-{uuid.uuid4().hex[:10]}"

    payload["session_id"] = sid

    prev_state = load_session(sid)
    if prev_state:
        merged = {**prev_state, **payload, "text": text}
        payload = merged

    out = router_graph.invoke(payload)

    new_state = {**payload, **out}
    save_session(sid, new_state)

    return {
        "answer": out.get("answer"),
        "session_id": sid,
        "active_route": new_state.get("active_route"),
    }

@app.get("/")
def home():
    """ 主页面 """
    return {"success": "success"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8002, reload=True)