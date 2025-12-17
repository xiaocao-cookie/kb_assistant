from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
import os
from jose import jwt
from typing import Any

PWD_CONTEXT = CryptContext(
    schemes=["bcrypt_sha256"],
    deprecated="auto",
)

JWT_SECRET = os.getenv("JWT_SECRET", "984454950")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

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
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
