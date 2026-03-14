"""MCP Server — exposes KB tools for Claude Code, Claude, and OpenClaw."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "kb",
    instructions="Personal knowledge base with RAG. Ingest URLs, query via semantic search.",
    host="127.0.0.1",
    port=4001,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:4001",
            "localhost:4001",
            "jones.quagga-chicken.ts.net",
            "jones.quagga-chicken.ts.net:443",
        ],
        allowed_origins=[
            "https://jones.quagga-chicken.ts.net",
        ],
    ),
)


@mcp.tool()
def ingest_url(url: str, notes: str | None = None) -> dict:
    """Ingest a URL into the knowledge base.

    Fetches the content, chunks it, generates embeddings, auto-tags,
    and stores everything in Supabase + markdown on disk.

    Args:
        url: The URL to ingest (http/https only).
        notes: Optional user commentary — weighted higher for tagging.

    Returns:
        Dict with source_id, title, source_type, tags, and chunk_count.
    """
    from kb.ingest.pipeline import ingest_url as _ingest_url

    result = _ingest_url(url, notes=notes)
    return result.model_dump(mode="json")


@mcp.tool()
def ingest_document(text: str, title: str, notes: str | None = None) -> dict:
    """Ingest raw text directly into the knowledge base.

    Args:
        text: The document text to ingest.
        title: A title for the document.
        notes: Optional user commentary — weighted higher for tagging.

    Returns:
        Dict with source_id, title, source_type, tags, and chunk_count.
    """
    from kb.ingest.pipeline import ingest_document as _ingest_document

    result = _ingest_document(text, title, notes=notes)
    return result.model_dump(mode="json")


@mcp.tool()
def query(
    question: str,
    match_count: int = 10,
    similarity_threshold: float = 0.0,
    tags: list[str] | None = None,
    source_type: str | None = None,
) -> list[dict]:
    """Search the knowledge base with a natural language question.

    Args:
        question: The search query.
        match_count: Max results to return (default 10).
        similarity_threshold: Minimum similarity score 0.0-1.0 (default 0.0).
        tags: Optional list of tags to filter by.
        source_type: Optional filter: article, youtube, tweet, pdf, document.

    Returns:
        List of matching chunks with source metadata, ordered by relevance.
    """
    from kb.query.engine import query as _query

    results = _query(
        question,
        match_count=match_count,
        similarity_threshold=similarity_threshold,
        tags=tags,
        source_type=source_type,
    )
    return [r.model_dump(mode="json") for r in results]


@mcp.tool()
def list_sources(
    source_type: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List ingested sources with optional filters.

    Args:
        source_type: Filter by type: article, youtube, tweet, pdf, document.
        tag: Filter by tag name.
        limit: Max results (default 50).

    Returns:
        List of sources with metadata and tags.
    """
    from kb.manage.ops import list_sources as _list_sources

    results = _list_sources(source_type=source_type, tag=tag, limit=limit)
    return [s.model_dump(mode="json") for s in results]


@mcp.tool()
def delete_source(source_id: str) -> dict:
    """Delete a source and all its chunks from the knowledge base.

    Args:
        source_id: UUID of the source to delete.

    Returns:
        Dict with deleted status.
    """
    from uuid import UUID

    from kb.manage.ops import delete_source as _delete_source

    success = _delete_source(UUID(source_id))
    return {"deleted": success, "source_id": source_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
