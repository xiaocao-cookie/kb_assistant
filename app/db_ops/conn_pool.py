import pymysql
from contextlib import contextmanager
from dbutils.pooled_db import PooledDB

from app.config import settings

pool = PooledDB(
    creator=pymysql,
    maxconnections=20,             # 最大连接数（核心参数）
    mincached=5,                   # 启动时创建的空闲连接
    maxcached=10,                  # 最大空闲连接
    blocking=True,                 # 连接用完是否阻塞等待
    host=settings.MYSQL_HOST,
    port=settings.MYSQL_PORT,
    user=settings.MYSQL_USER,
    password=settings.MYSQL_PASSWORD,
    database=settings.MYSQL_DB,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)

@contextmanager
def get_conn():
    """ 获取数据库连接 """
    conn = pool.connection()
    try:
        yield conn
    finally:
        conn.close()
