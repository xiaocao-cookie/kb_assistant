import pymysql
from contextlib import contextmanager
from app.config import settings

@contextmanager
def get_conn():
    """ 获取数据库连接 """
    # todo: 考虑增加数据库连接池
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
