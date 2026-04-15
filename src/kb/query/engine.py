"""Semantic search — embed question, call search_chunks, return ranked results."""

from __future__ import annotations

from psycopg.rows import dict_row

from kb.db import get_pool
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
    """Search the knowledge base with a natural language question.

    Args:
        question: The search query.
        match_count: Max number of results to return.
        similarity_threshold: Minimum cosine similarity (0.0 to 1.0).
        tags: Optional tag filter — results must have at least one matching tag.
        source_type: Optional filter by source type (article, youtube, tweet, pdf, document).

    Returns:
        List of QueryResult objects, ordered by similarity descending.
    """
    query_embedding = embed(question)

    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM search_chunks(%s::vector, %s, %s, %s, %s)",
            (query_embedding, match_count, similarity_threshold, tags, source_type),
        )
        return [QueryResult(**row) for row in cur.fetchall()]
