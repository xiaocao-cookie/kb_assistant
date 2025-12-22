from fastapi import APIRouter, Header, Depends, HTTPException, status

from app.model.auth_model import UserInDB, LoginReq, RegisterReq, TokenResp
from app.service.auth_service import verify_password, create_access_token, decode_token, extend_token_exp
from app.db_ops.auth_sql import get_user_by_id, get_user_by_username, update_last_login, create_user

auth_router = APIRouter(
    prefix="/auth",
    tags=["用户认证"]
)


def get_current_user(authorization: str | None = Header(default=None)) -> UserInDB:
    """
    根据 authorization 获取当前用户

    :param authorization: HTTP 请求头（Header）中的 Authorization 字段, 常用格式为 Bearer <token>
    :return: Pydantic 的 Model，用来描述 User 表
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺失 Bearer Token")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 无效")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 中无 sub 字段")

    user = get_user_by_id(int(user_id))
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或未激活")

    return UserInDB(
        id=int(user["id"]),
        username=user["username"],
        email=user.get("email"),
        phone=user.get("phone"),
        full_name=user.get("full_name"),
        is_active=bool(user["is_active"]),
        is_super_admin=bool(user["is_super_admin"])
    )


def get_current_user_optional(authorization: str | None = Header(default=None, alias="Authorization")) -> UserInDB | None:
    """
    根据 authorization 获取当前用户, 如果无 authorization 也不引发异常，兼容用户未授权的情况

    :param authorization: HTTP 请求头（Header）中的 Authorization 字段，常用格式为 Bearer <token>
    :return: Pydantic 的 Model，用来描述 User 表 或 None
    """
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None

    try:
        return get_current_user(authorization)
    except Exception:
        return None                                     # 这里不是错写，而是兼容未登录的情况，也称作软鉴权


@auth_router.post("/register", response_model=UserInDB)
def register(req: RegisterReq):
    """ 用户注册 """
    if get_user_by_username(req.username):
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = create_user(req)
    return UserInDB(
        id=int(user["id"]),
        username=user["username"],
        email=user.get("email"),
        phone=user.get("phone"),
        full_name=user.get("full_name"),
        is_active=bool(user["is_active"]),
        is_super_admin=bool(user["is_super_admin"])
    )


@auth_router.post("/login", response_model=TokenResp)
def login(req: LoginReq, authorization: str | None = Header(default=None)):
    """ 用户登录 """
    user = get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名不存在")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="密码不正确")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="用户未激活")

    payload = {"sub": str(user["id"]), "name": user["username"]}
    if not authorization:
        token = create_access_token(payload)
    else:
        token = extend_token_exp(authorization.split(" ")[1])


    ok = update_last_login(int(user["id"]))
    if not ok:
        raise HTTPException(status_code=500, detail="数据更新失败")

    return TokenResp(access_token=token)


@auth_router.get("/me", response_model=UserInDB)
def me(current_user: UserInDB = Depends(get_current_user)):
    """ 获取当前登录用户 """
    return current_user
