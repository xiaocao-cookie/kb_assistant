from typing import List

from pydantic import BaseModel


class SetRolePermsReq(BaseModel):
    """ 设置角色权限的请求体 """
    perm_codes: List[str]

class SetUserRolesReq(BaseModel):
    """ 设置用户角色的请求体 """
    role_codes: List[str]