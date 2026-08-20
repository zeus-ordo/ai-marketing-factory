import psycopg2
from psycopg2 import pool
import threading
from contextlib import contextmanager
from typing import Generator

_pool: pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def init_pool(dsn: str) -> None:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = pool.ThreadedConnectionPool(minconn=2, maxconn=10, dsn=dsn)


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool:
            _pool.closeall()
            _pool = None


@contextmanager
def get_connection() -> Generator:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
