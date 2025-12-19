from app.model.auth_model import UserInDB
from app.db_ops.rbac_sql import get_user_permissions
from app.api.auth_api import get_current_user

from typing import Iterable, Any, Callable

from fastapi import HTTPException, status, Depends


def _resolve_perms(*,
                   user: UserInDB | None = None,
                   user_id: int | None = None,
                   perms: Iterable[str] | None = None) -> set[str]:
    """
    根据 user/user_id/perms 解析用户的权限，并返回权限的集合

    :param user: 用户实体类，对应 UserInDB
    :param user_id: 用户ID
    :param perms: 权限
    :return: 解析后的权限集合
    """

    if perms:
        return set(perms)

    if user:
        p = getattr(user, "permission", None)
        if p:
            return set(p)
        user_id = user_id or getattr(user, "id", None)

    if user_id:
        return set(get_user_permissions(int(user_id)))

    return set()


def _raise_403(detail: str) -> None:
    """
    引发 403 异常，并添加 detail 说明

    :param detail: 异常说明
    :return: None
    """

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_permission(subject: Any, required_perm: str | None = None) -> Callable | None:
    """
    权限校验，适用于依赖注入和立即校验两种场景

    :param subject:
            - str: 表示权限编码，用于依赖注入，且 required_perm 为 None 时才生效
            - UserInDB / dict: 代表用户，校验用户是否有对应的权限
    :param required_perm: 待校验的权限编码，当 subject 不为 str 时必填
    :return:
        - Callable: 用于依赖注入的 Depends 函数
        - None: 校验通过放行，否则引发异常
    """
    # todo： 考虑是否拆成两个函数
    if isinstance(subject, str) and required_perm is None:
        perm_code = subject

        def _checker(current_user: UserInDB = Depends(get_current_user)):
            if getattr(current_user, "is_super_admin", False):
                return True
            if perm_code not in _resolve_perms(user=current_user):
                _raise_403(f"无 {perm_code} 权限")
            return True

        return _checker

    user = subject
    perm_code = required_perm
    if not perm_code or not isinstance(perm_code, str):
        raise TypeError(f"{perm_code} 必须是 str")

    if isinstance(user, dict):
        if user.get("is_super_admin"):
            return None
        perm_set = _resolve_perms(user_id=user.get("user_id"), perms=user.get("permissions"))
        if perm_code not in perm_set:
            _raise_403(f"无 {perm_code} 权限")
        return None

    if getattr(user, "is_super_admin", False):
        return None
    perm_set = _resolve_perms(user=user)
    if perm_code not in perm_set:
        _raise_403(f"无 {perm_code} 权限")
    return None


def check_permission(user: Any, perm_code: str) -> None:
    """
    校验 user 是否有 perm_code 权限，超级管理员越过检查

    :param user: 用户
    :param perm_code: 权限编码
    :return: 若有权限，则通过，否则抛出异常
    """

    if not perm_code or not isinstance(perm_code, str):
        raise TypeError("perm_code 必须是一个非空的 str")

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"用户 {user} 未授权")

    if isinstance(user, dict):
        if user.get("is_super_admin", False):
            return None
        perms = set(user.get("permissions") or [])
        if perm_code not in perms:
            _raise_403(f"无 {perm_code} 权限")
        return None

    if getattr(user, "is_super_admin", False):
        return None

    perms = set(getattr(user, "permissions", []) or [])
    if not perms:
        user_id = getattr(user, "id", None)
        if not user_id:
            _raise_403(f"非法用户 {user}")
        perms = set(get_user_permissions(user_id))

    if perm_code not in perms:
        _raise_403(f"无 {perm_code} 权限")
    return None


def has_permission(*,
                   user_id: int | None = None,
                   perms: Iterable[str] | None,
                   perm_code: str) -> bool:
    """
    判定是否拥有指定权限

    1. 查询某个用户（通过 user_id 获取）是否有 perm_code 权限
    2. 查询 perm_code 是否在给定的 perms 中

    :param user_id: 用户 ID
    :param perms: 已解析好的权限集合，可能来自 JWT/上下文缓存
    :param perm_code: 待校验的权限编码
    :return: 若有该权限返回 True, 否则返回 False
    """

    resolved_perm_set = _resolve_perms(user_id=user_id, perms=perms)
    return perm_code in resolved_perm_set


def allowed_kb_visibilities(perms: Iterable[str] | None) -> list[str]:
    """
    根据 perms 解析知识库的可见性范围

    :param perms: 权限的集合/列表
    :return: 允许访问的知识库范围
    """

    p = set(perms or [])
    allowed = ["public"]
    if "kb.view_internal" in p or "kb.manage_docs" in p:
        allowed.append("internal")
    return allowed


