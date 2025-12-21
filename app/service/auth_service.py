from datetime import datetime, timezone, timedelta
from typing import Any
import os

from passlib.context import CryptContext
from jose import jwt
from jwt import ExpiredSignatureError, InvalidTokenError


PWD_CONTEXT = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto",
)

JWT_SECRET = os.getenv("JWT_SECRET", "984454950")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))
JWT_EXTEND_EXPIRE_MINUTES = int(os.getenv("JWT_EXTEND_EXPIRE_MINUTES", "60"))


def hash_password(password: str) -> str:
    """
    密码加密
    """
    return PWD_CONTEXT.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """
    密码验证
    :param plain: 原密码
    :param hashed:  加密后的密码
    :return: 校验是否通过
    """
    return PWD_CONTEXT.verify(plain, hashed)


def create_access_token(payload: dict[str, Any], expires_minutes: int | None = None) -> str:
    """
    创建一个访问令牌
    :param payload: 载荷
    :param expires_minutes: 过期时间
    :return: JWT的token
    """
    minutes = expires_minutes or JWT_EXPIRE_MINUTES
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
    to_encoded = {**payload, "exp": expire}
    return jwt.encode(to_encoded, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict[str, Any]:
    """
    解码 JWT的 token
    """
    return jwt.decode(token, JWT_SECRET, algorithms=JWT_ALG)


def extend_token_exp(token: str) -> str:
    """
    每次登录后，通过新建 token 的方式延长 原token 的有效期，原token 自动过期即可

    :param token: 原 Token
    :return: 延长过期时间的 token, 默认延长 JWT_EXTEND_EXPIRE_MINUTES（60 分钟）
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, JWT_ALG)
    except ExpiredSignatureError:
        raise
    except InvalidTokenError:
        raise

    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXTEND_EXPIRE_MINUTES)

    return jwt.encode(payload, JWT_SECRET, JWT_ALG)

