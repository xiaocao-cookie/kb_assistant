from fastapi import APIRouter, Depends, HTTPException

from typing import Optional

from app.model.rbac_model import SetRolePermsReq, SetUserRolesReq
from app.service.rbac_service import require_permission
from app.constants.rbac import Permission
from app.db_ops.rbac_sql import (
    list_roles,
    list_module_permissions,
    get_role_permissions,
    set_role_permissions,
    find_user_id,
    get_user_roles,
    set_user_roles
)


rbac_roles_router = APIRouter(
    prefix="/rbac",
    tags=["RBAC - system.manage_roles: 配置角色的权限"],
    dependencies=[
        Depends(require_permission(Permission.PERM_SYSTEM_MANAGE_ROLES)),
    ]
)

rbac_users_router = APIRouter(
    prefix="/rbac",
    tags=["RBAC - system.manage_users: 管理用户的权限"],
    dependencies=[
        Depends(require_permission(Permission.PERM_SYSTEM_MANAGE_USERS))
    ]
)


@rbac_roles_router.get("/list_roles")
def api_list_roles():
    """ 列出所有角色 """
    return {"roles": list_roles()}


@rbac_roles_router.get("/list_permissions")
def api_list_permissions(module: Optional[str] = None):
    """ 根据 module（可选） 列出对应权限 """
    return {"permissions": list_module_permissions(module)}


@rbac_roles_router.get("/roles/{role_code}/permissions")
def api_get_role_permission(role_code: str):
    """ 根据 role_code 查询对应的权限 """
    return {"role": role_code, "permissions": get_role_permissions(role_code)}


@rbac_roles_router.put("/roles/{role_code}/permissions")
def api_set_role_permission(role_code: str, req: SetRolePermsReq):
    """ 为 role_code 对应的角色新增权限 """
    try:
        set_role_permissions(role_code, req.perm_codes)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))

    return {"ok": True, "role": role_code, "permissions": get_role_permissions(role_code)}


@rbac_users_router.get("/users/{username}/roles")
def api_get_user_roles(username: str):
    """ 根据 username 获取用户角色 """
    user_id = find_user_id(username)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"数据库中无 {username} 用户")
    return {"user": username, "user_id": user_id, "roles": get_user_roles(user_id)}


@rbac_users_router.put("/users/{username}/roles")
def api_set_user_roles(username: str, req: SetUserRolesReq):
    """ 给 username 用户设置角色 """
    user_id = find_user_id(username)
    if not user_id:
        raise HTTPException(status_code=404, detail=f"数据库中无 {username} 用户")
    set_user_roles(user_id, req.role_codes)
    return {"ok": True, "user": username, "user_id": user_id, "roles": get_user_roles(user_id)}