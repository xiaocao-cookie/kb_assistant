from pydantic import BaseModel, EmailStr
from typing import Optional

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