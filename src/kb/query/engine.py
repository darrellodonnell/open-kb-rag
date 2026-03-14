"""Semantic search — embed question, call search_chunks RPC, return ranked results."""

from __future__ import annotations

from kb.db import get_client
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
    # Embed the question
    query_embedding = embed(question)

    # Call the search_chunks RPC
    client = get_client()
    params = {
        "query_embedding": query_embedding,
        "match_count": match_count,
        "similarity_threshold": similarity_threshold,
    }
    if tags:
        params["filter_tags"] = tags
    if source_type:
        params["filter_source_type"] = source_type

    result = client.rpc("search_chunks", params).execute()

    return [QueryResult(**row) for row in result.data]
