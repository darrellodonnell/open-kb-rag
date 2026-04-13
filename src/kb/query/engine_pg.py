"""Semantic search against local PostgreSQL (psycopg path)."""

from __future__ import annotations

from psycopg.rows import dict_row

from kb.db_pg import get_pool
from kb.ingest.embeddings import embed
from kb.models import QueryResult


def query(
    question: str,
    *,
    match_count: int = 10,
    similarity_threshold: float = 0.0,
    tags: list[str] | None = None,
    source_type: str | None = None,
) -> list[QueryResult]:
    query_embedding = embed(question)

    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM search_chunks(%s::vector, %s, %s, %s, %s)",
            (query_embedding, match_count, similarity_threshold, tags, source_type),
        )
        return [QueryResult(**row) for row in cur.fetchall()]
