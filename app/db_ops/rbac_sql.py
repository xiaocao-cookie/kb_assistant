from app.db_ops.conn_pool import get_conn
from app.model.rbac_model import RoleReq

from typing import Optional


def _get_role_id(role_code: str) -> Optional[int]:
    """
    根据 role_code 获取对应的 role_id

    :param role_code: 角色编码
    :return: 角色主键 ID
    """
    sql = """
    SELECT id FROM roles WHERE code = %s LIMIT 1
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (role_code, ))
            row = cur.fetchone()

    return int(row["id"]) if row else None


def get_user_roles(user_id: int) -> list[str]:
    """
    根据 user_id 查询用户角色

    :param user_id: 用户 ID
    :return: 角色的列表
    """
    sql = """
          SELECT r.code
          FROM roles r 
                   JOIN user_roles ur ON ur.role_id = r.id
          WHERE ur.user_id = %s
          GROUP BY r.code
          ORDER BY r.code
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            rows = cur.fetchall()
    return [r["code"] for r in rows]


def get_user_permissions(user_id: int) -> set[str]:
    """
    根据 user_id 获取用户的权限编码

    :param user_id: 用户 ID
    :return: 该用户权限编码的集合
    """
    sql = """
          SELECT p.code
          FROM permissions p
                   JOIN role_permissions rp ON rp.permission_id = p.id
                   JOIN user_roles ur ON ur.role_id = rp.role_id
          WHERE ur.user_id = %s
          GROUP BY p.code
          ORDER BY p.code
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, ))
            rows = cur.fetchall()

    return {r["code"] for r in rows}


def find_user_id(username: str) -> Optional[int]:
    """
    根据 username 查询用户 ID

    :param username: 用户名
    :return: 用户主键 ID
    """
    sql = """
    SELECT id FROM users WHERE username=%s LIMIT 1
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (username, ))
            row = cur.fetchone()

    return int(row["id"]) if row else None


def list_roles() -> list[dict]:
    """
    列出 roles 表中的所有数据
    """
    sql = """
    SELECT id, code, name, description, is_system FROM roles ORDER BY code
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()


def set_roles(role_model: RoleReq) -> None:
    """
    根据 role_model 新建角色
    :param role_model: 角色的 Model
    :return: None
    """
    sql = """
          INSERT IGNORE INTO roles (code, name, description, is_system)
          VALUES (%s, %s, %s, %s)
          """

    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql, (
                    role_model.code,
                    role_model.name,
                    role_model.description,
                    role_model.is_system
                ))
            except Exception:
                raise



def list_module_permissions(module: Optional[str] = None) -> list[dict]:
    """
    根据  module 列出所有的权限

    :param module: 权限的模块名
    :return: 每一项权限的列表
    """
    sql = """
    SELECT id, code, name, module, description FROM permissions 
    """
    args = []
    if module:
        sql += "WHERE module = %s "
        args.append(module)
    sql += "ORDER BY module, code"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(args))
            return cur.fetchall()


def get_role_permissions(role_code: str) -> list[str]:
    """
    根据 role_code 获取对应的 permission_code

    :param role_code: 角色编码
    :return: 权限编码
    """
    sql = """
          SELECT p.code
          FROM permissions p
                   JOIN role_permissions rp ON rp.permission_id = p.id
                   JOIN roles r ON r.id = rp.role_id
          WHERE r.code = %s
          ORDER BY p.code
          """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (role_code,))
            rows = cur.fetchall()
    return [r["code"] for r in rows]


def set_role_permissions(role_code: str, perm_codes: list[str]) -> None:
    """
    给 role_code 对应的角色新增 perm_codes 权限

    :param role_code: 角色编码
    :param perm_codes: 权限编码的列表
    :return: None
    """
    role_id = _get_role_id(role_code)
    if role_id is None:
        raise ValueError(f"系统中无此 {role_code} 角色, 请先新建此 {role_code} 角色")

    perm_codes = sorted(set([p.strip() for p in (perm_codes or []) if p and p.strip()]))

    perm_code_to_id: dict[str, int] = {}
    if perm_codes:
        placeholders = ",".join(["%s"] * len(perm_codes))
        sql = f"SELECT id, code FROM permissions WHERE code IN ({placeholders})"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(perm_codes))
                for row in cur.fetchall():
                    perm_code_to_id[row["code"]] = int(row["id"])

        missing = [c for c in perm_codes if c not in perm_code_to_id]
        if missing:
            raise ValueError(f"未知权限编码: {missing}")

    role_permission_sql = """
    INSERT IGNORE INTO role_permissions (role_id, permission_id) VALUES (%s,%s)
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            for code in perm_codes:
                cur.execute(
                    role_permission_sql, (role_id, perm_code_to_id[code])
                )


def set_user_roles(user_id: int, role_codes: list[str]) -> None:
    """
    根据 user_id 和 role_codes 设置用户的角色，如果 role_codes 为空，默认赋予 public 角色编码

    :param user_id: 用户 ID
    :param role_codes: 角色编码的的列表
    :return: None
    """
    role_codes = [r.strip() for r in (role_codes or []) if r and r.strip()]
    if not role_codes:
        role_codes = ["public"]
    role_codes = sorted(set(role_codes))

    placeholders = ",".join(["%s"] * len(role_codes))
    sql = f"""
    SELECT id, code FROM roles WHERE code IN ({placeholders})
    """

    role_code_to_id: dict[str, int] = {}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(role_codes))
            for row in cur.fetchall():
                role_code_to_id[row["code"]] = int(row["id"])

    missing = [c for c in role_codes if c not in role_code_to_id]
    if missing:
        raise ValueError(f"未知的角色编码: {missing}")

    user_role_sql = """
    INSERT IGNORE INTO user_roles (user_id, role_id) VALUES (%s,%s)
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            for code in role_codes:
                cur.execute(
                    user_role_sql,
                    (user_id, role_code_to_id[code]),
                )

