"""Storage — write markdown to disk + insert source/chunks/tags to Supabase."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from kb.config import settings
from kb.db import get_client


def write_markdown(title: str, content: str, notes: str | None = None) -> str:
    """Write content as a markdown file to KB storage.

    Returns the relative path from KB_STORAGE_PATH.
    """
    now = datetime.now(timezone.utc)
    year = now.strftime("%Y")
    month = now.strftime("%m")

    # Sanitize title for filesystem
    safe_title = _slugify(title)
    dir_path = settings.kb_storage_path / year / month
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / f"{safe_title}.md"

    # Handle duplicates by appending a counter
    counter = 1
    while file_path.exists():
        file_path = dir_path / f"{safe_title}-{counter}.md"
        counter += 1

    # Build markdown content
    parts: list[str] = [f"# {title}\n"]
    if notes:
        parts.append(f"## Notes\n\n{notes}\n")
    parts.append(f"## Content\n\n{content}\n")

    file_path.write_text("\n".join(parts), encoding="utf-8")

    return f"{year}/{month}/{file_path.name}"


def store_source(
    *,
    url: str | None,
    title: str,
    source_type: str,
    notes: str | None,
    chunk_count: int,
    markdown_path: str | None,
    metadata: dict,
) -> UUID:
    """Insert a source record and return its UUID."""
    if settings.db_backend == "postgres":
        from kb.ingest.storage_pg import store_source as _pg

        return _pg(
            url=url,
            title=title,
            source_type=source_type,
            notes=notes,
            chunk_count=chunk_count,
            markdown_path=markdown_path,
            metadata=metadata,
        )
    client = get_client()
    result = (
        client.table("sources")
        .insert(
            {
                "url": url,
                "title": title,
                "source_type": source_type,
                "notes": notes,
                "chunk_count": chunk_count,
                "markdown_path": markdown_path,
                "metadata": metadata,
            }
        )
        .execute()
    )
    return UUID(result.data[0]["id"])


def store_chunks(
    source_id: UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    content_type: str,
) -> None:
    """Insert chunk records with embeddings."""
    if settings.db_backend == "postgres":
        from kb.ingest.storage_pg import store_chunks as _pg

        return _pg(source_id, chunks, embeddings, content_type)
    client = get_client()
    from kb.ingest.chunker import count_tokens

    rows = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        rows.append(
            {
                "source_id": str(source_id),
                "chunk_index": i,
                "content": chunk,
                "content_type": content_type,
                "token_count": count_tokens(chunk),
                "embedding": emb,
            }
        )

    # Insert in batches to avoid payload limits
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("chunks").insert(batch).execute()


def store_tags(source_id: UUID, tags: list[str]) -> None:
    """Insert tags and link them to the source via source_tags."""
    if not tags:
        return

    if settings.db_backend == "postgres":
        from kb.ingest.storage_pg import store_tags as _pg

        return _pg(source_id, tags)

    client = get_client()

    # Batch upsert all tags at once
    tag_rows = [{"name": t} for t in tags]
    tag_result = client.table("tags").upsert(tag_rows, on_conflict="name").execute()

    # Batch link all tags to the source
    link_rows = [
        {"source_id": str(source_id), "tag_id": row["id"]}
        for row in tag_result.data
    ]
    if link_rows:
        client.table("source_tags").upsert(
            link_rows, on_conflict="source_id,tag_id"
        ).execute()


def _slugify(text: str, max_length: int = 80) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_length] or "untitled"
