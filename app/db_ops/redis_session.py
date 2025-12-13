import json
import redis
from typing import Any

r = redis.Redis(
    host="127.0.0.1",
    port=6379,
    decode_responses=True,
)

TTL_SECONDS = 86400 * 2  # 2 days

# Keys that often contain non-JSON-serializable objects (LangChain Documents, Messages, etc.)
DROP_KEYS = {"docs", "messages", "chat_history", "retrieved_docs"}


def _safe_dumps(obj: Any) -> str:
    """ 将 obj 转为 str """
    return json.dumps(obj, ensure_ascii=False, default=str)


def load_session(session_id: str) -> dict | None:
    """ 将 session_id 所对应的值转换为字典 """
    s = r.get(session_id)
    return json.loads(s) if s else None


def save_session(session_id: str, state: dict) -> None:
    """ 将不可序列化的字段排除 """
    safe_state = {k: v for k, v in state.items() if k not in DROP_KEYS}
    r.setex(session_id, TTL_SECONDS, _safe_dumps(safe_state))
