import pymysql
from contextlib import contextmanager
from app.config import settings


@contextmanager
def get_conn():
    """ 获取数据库连接 """
    conn = pymysql.connect(
        host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DB, charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        yield conn
    finally:
        conn.close()


def get_leave_balance(requester: str) -> dict | None:
    """ 查询 requester 的假期余额 """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT annual_days, sick_days, personal_days FROM leave_balances WHERE requester=%s",
                (requester,)
            )
            return cur.fetchone()


def insert_leave_request(req: dict) -> str:
    """
    往 leave_requests 插入一条请假单记录
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests
                (leave_id, requester, leave_type, start_time, end_time, duration_days, reason, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'PENDING')
                """,
                (
                    req["leave_id"], req["requester"], req["leave_type"],
                    req["start_time"], req["end_time"], req["duration_days"],
                    req.get("reason")
                )
            )
    return req["leave_id"]


def insert_annual_leave_request(req: dict) -> str:
    """
    往 leave_requests 插入一条请假单记录
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests
                (leave_id, requester, leave_type, start_time, end_time, duration_days, reason, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'APPROVED')
                """,
                (
                    req["leave_id"], req["requester"], req["leave_type"],
                    req["start_time"], req["end_time"], req["duration_days"],
                    req.get("reason")
                )
            )
    return req["leave_id"]

def get_leave_request(leave_id: str) -> dict | None:
    """ 根据 leave_id 查询请假单 """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM leave_requests WHERE leave_id=%s", (leave_id,))
            return cur.fetchone()


def cancel_leave_request(leave_id: str) -> bool:
    """ 根据 leave_id 将请假状态改为 CANCELLED """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leave_requests SET status='CANCELLED' WHERE leave_id=%s AND status='PENDING'",
                (leave_id,)
            )
            return cur.rowcount > 0

def get_recent_leave_requests(requester: str, limit: int = 5) -> list[dict]:
    """
    查询 requester 的最近 limit 条的查询记录
    """
    limit = max(1, min(int(limit), 20))  # 我们查询的时候最多一次查询20条
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT leave_id, leave_type, start_time, end_time, duration_days, status, reason, created_at "
                "FROM leave_requests WHERE requester=%s "
                "ORDER BY id DESC LIMIT %s",
                (requester, limit),
            )
            return cur.fetchall()


def update_leave_request(leave_id: str, fields: dict) -> bool:
    """
    根据请假单的 leave_id 更新允许修改的 fields
    """
    allowed = {"leave_type", "start_time", "end_time", "duration_days", "reason"}
    sets = []
    params = []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=%s")
            params.append(v)

    if not sets:
        return False

    params.extend([leave_id])
    sql = (
        "UPDATE leave_requests SET " + ", ".join(sets) +
        " WHERE leave_id=%s AND status='PENDING'"
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            return cur.rowcount > 0


def approve_leave_request(leave_id: str, approver: str) -> bool:
    """
    approver 根据 leave_id 批准请假单
    :param leave_id: 请假单ID
    :param approver: 审批人
    :return: 是否批准
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leave_requests SET status='APPROVED' "
                "WHERE leave_id=%s AND status='PENDING'",
                (leave_id,),
            )
            return cur.rowcount > 0


def reject_leave_request(leave_id: str, approver: str, reason: str | None = None) -> bool:
    """
    approver 根据 leave_id 驳回请假，并陈述驳回的 reason
    :param leave_id: 请假单 ID
    :param approver: 审批人
    :param reason: 驳回理由
    :return: 是否驳回
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leave_requests "
                "SET status='REJECTED', reason=COALESCE(%s, reason) "
                "WHERE leave_id=%s AND status='PENDING'",
                (reason, leave_id),
            )
            return cur.rowcount > 0