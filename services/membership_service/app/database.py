import psycopg2
from psycopg2 import pool
import threading
import re
from contextlib import contextmanager
from typing import Generator

_pool: pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _parse_dsn(dsn: str) -> dict:
    """Parse postgresql:// URI into psycopg2 connection kwargs."""
    # Handles: postgresql://user:pass@host:port/dbname
    match = re.match(r'postgresql://([^:@]+):([^@]+)@([^:/]+)(?::(\d+))?/(.+)', dsn)
    if not match:
        raise ValueError(f"Cannot parse DSN: {dsn}")
    user, password, host, port, dbname = match.groups()
    return {
        'host': host,
        'port': int(port) if port else 5432,
        'dbname': dbname,
        'user': user,
        'password': password,
        'connect_timeout': 10,
    }


def init_pool(dsn: str) -> None:
    global _pool
    with _pool_lock:
        if _pool is None:
            kwargs = _parse_dsn(dsn)
            _pool = pool.ThreadedConnectionPool(minconn=2, maxconn=10, **kwargs)


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
