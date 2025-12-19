from app.db_ops.conn_pool import get_conn
from app.api.auth_api import RegisterReq
from app.security import hash_password

from typing import List, Set
from datetime import datetime, timezone

def get_user_roles(user_id: int) -> List[str]:
    """
    根据 user_id 查询用户角色
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


def get_user_permissions(user_id: int) -> Set[str]:
    """
    根据 user_id 查询用户权限
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
            cur.execute(sql, (user_id,))
            rows = cur.fetchall()
    return {r["code"] for r in rows}


def get_user_by_username(username: str) -> dict:
    """ 通过 username 查询某个用户(精确查询) """
    sql = """ SELECT * FROM users WHERE username = %s LIMIT 1 """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (username, ))
            return cur.fetchone()


def get_user_by_id(user_id: int) -> dict:
    """ 通过 user_id 获取用户 """
    sql = """
    SELECT * FROM users WHERE id = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id, ))
            return cur.fetchone()


def update_last_login(user_id) -> bool:
    """
    根据 user_id 更新用户最后一次登录的时间
    :param user_id: 用户id
    :return: 是否更新成功
    """
    # todo： 每次登录后再重新刷新一下 token 的有效期，有效期根据此时间增加 timedelta
    sql = """
    UPDATE users SET last_login_at = %s WHERE id = %s
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (datetime.now(timezone.utc), user_id))
            return cur.rowcount == 1


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