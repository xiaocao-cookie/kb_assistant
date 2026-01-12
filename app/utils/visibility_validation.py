from fastapi import HTTPException

from app.db_ops.kb_sql import get_allowed_visibilities


def parse_visibility(v: str) -> str:
    """
    可见性参数校验
    """
    v = (v or "").strip().lower()
    if v not in get_allowed_visibilities():
        raise HTTPException(status_code=400, detail=f"无效的可见性 {v}")
    return v