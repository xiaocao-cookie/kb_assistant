from fastapi import APIRouter, Header, Depends, HTTPException, status

from pydantic import BaseModel, EmailStr
from typing import Optional


from app.db_ops.conn_pool import get_conn
from app.security import hash_password, verify_password, create_access_token, decode_token
from app.db_ops.user_sql import get_user_by_id, get_user_by_username, update_last_login

auth_router = APIRouter(prefix="/auth")


class RegisterReq(BaseModel):
    """ 用户注册的请求体 """
    username: str
    password: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None


class LoginReq(BaseModel):
    """ 用户登陆的请求体 """
    username: str
    password: str


class TokenResp(BaseModel):
    """ Token 的响应体 """
    access_token: str
    token_type: str = "bearer"


class UserInDB(BaseModel):
    """ ORM映射，对应 User 表的部分字段 """
    id: int
    username: str
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    is_super_admin: bool



def create_user(user: RegisterReq) -> dict:
    """
    使用前端传过来的 user 新建用户并赋予 public 权限
    :param user: 用户注册的请求体
    :return: 创建好的用户
    """
    password_hash = hash_password(user.password)
    sql = """
          INSERT INTO users (username, email, phone, password_hash, full_name, is_active, is_super_admin)
          VALUES (%s, %s, %s, %s, %s, 1, 0)
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                user.username,
                user.email,
                user.phone,
                password_hash,
                user.full_name
            ))
            user_id = cur.lastrowid             # 获取上一行的自增主键，只有主键自增时有效

    auth_role_sql = """
    INSERT IGNORE INTO user_roles (user_id, role_id)
    SELECT %s, r.id FROM roles r where r.code = 'public'
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(auth_role_sql, (user_id, ))

    u = get_user_by_id(user_id)
    return u


def get_current_user(authorization: str | None = Header(default=None, alias="Authorization")) -> UserInDB:
    """
    根据 authorization 获取当前用户
    :param authorization: HTTP 请求头（Header）中的 Authorization 字段, 常用格式为 Bearer <token>
    :return: Pydantic 的 Model，用来描述 User 表
    """
    print(f"==================={authorization}===================================")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺失 Bearer Token")

    token = authorization.split(" ", 1)[1].strip()
    print(f"==================={token}=======================")
    try:
        payload = decode_token(token)
        print(f"=============={payload}======================")
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
def login(req: LoginReq):
    """ 用户登陆 """
    user = get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名不存在")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="密码不正确")

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="用户未激活")

    ok = update_last_login(int(user["id"]))
    if not ok:
        raise HTTPException(status_code=500, detail="数据更新失败")

    payload = {"sub": str(user["id"]), "name": user["username"]}
    token = create_access_token(payload)
    return TokenResp(access_token=token)


@auth_router.get("/me", response_model=UserInDB)
def me(current_user: UserInDB = Depends(get_current_user)):
    """ 获取当前登陆用户 """
    return current_user
