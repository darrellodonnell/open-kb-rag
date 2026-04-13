"""Storage operations against local PostgreSQL (psycopg path)."""

from __future__ import annotations

from uuid import UUID

from psycopg.types.json import Jsonb

from kb.db_pg import get_pool


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
