"""Storage — write markdown to disk + insert source/chunks/tags to PostgreSQL."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from kb.config import settings
from kb.db import get_pool


def write_markdown(title: str, content: str, notes: str | None = None) -> str:
    """Write content as a markdown file to KB storage.

    Returns the relative path from KB_STORAGE_PATH.
    """
    now = datetime.now(timezone.utc)
    year = now.strftime("%Y")
    month = now.strftime("%m")

    safe_title = _slugify(title)
    dir_path = settings.kb_storage_path / year / month
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / f"{safe_title}.md"

    counter = 1
    while file_path.exists():
        file_path = dir_path / f"{safe_title}-{counter}.md"
        counter += 1

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
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources
              (url, title, source_type, notes, chunk_count, markdown_path, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (url, title, source_type, notes, chunk_count, markdown_path, Jsonb(metadata)),
        )
        return cur.fetchone()[0]


def store_chunks(
    source_id: UUID,
    chunks: list[str],
    embeddings: list[list[float]],
    content_type: str,
) -> None:
    """Insert chunk records with embeddings."""
    from kb.ingest.chunker import count_tokens

    rows = [
        (str(source_id), i, chunk, content_type, count_tokens(chunk), emb)
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks
              (source_id, chunk_index, content, content_type, token_count, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )


def store_tags(source_id: UUID, tags: list[str]) -> None:
    """Insert tags and link them to the source via source_tags."""
    if not tags:
        return

    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        tag_ids: list[int] = []
        for tag in tags:
            cur.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag,),
            )
            tag_ids.append(cur.fetchone()[0])

        cur.executemany(
            """
            INSERT INTO source_tags (source_id, tag_id) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            [(str(source_id), tag_id) for tag_id in tag_ids],
        )


def _slugify(text: str, max_length: int = 80) -> str:
    """Convert text to a filesystem-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_length] or "untitled"
