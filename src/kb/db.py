"""PostgreSQL connection pool (psycopg 3) with pgvector adapter."""

from __future__ import annotations

from functools import lru_cache

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from kb.config import settings


def _configure(conn) -> None:
    register_vector(conn)


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    pool = ConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=8,
        configure=_configure,
        kwargs={"application_name": "open-kb-rag"},
        open=True,
    )
    pool.wait(timeout=5)
    return pool
