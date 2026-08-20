import psycopg
import psycopg.rows
from psycopg_pool import ConnectionPool as Pool
import threading
from contextlib import contextmanager
from typing import Generator

_pool: Pool | None = None
_pool_lock = threading.Lock()


def init_pool(dsn: str) -> None:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = Pool(dsn, min_size=2, max_size=10)


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool:
            _pool.close()
            _pool = None


@contextmanager
def get_connection() -> Generator:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    with _pool.connection() as conn:
        conn.row_factory = psycopg.rows.dict_row
        yield conn
