"""Postgres access: one connection pool, explicit transactions, dict rows."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def init_pool(url: str | None = None, max_size: int = 10) -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(url or get_settings().database_url, min_size=1, max_size=max_size,
                               kwargs={"row_factory": dict_row, "autocommit": False}, open=True)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tx() -> Iterator[Connection]:
    """A connection inside one transaction. Commits on success, rolls back on error."""
    pool = init_pool()
    with pool.connection() as conn:
        with conn.transaction():
            yield conn
