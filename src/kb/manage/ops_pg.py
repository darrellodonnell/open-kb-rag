"""Management ops against local PostgreSQL (psycopg path)."""

from __future__ import annotations

import logging
from uuid import UUID

from psycopg.rows import dict_row

from kb.config import settings
from kb.db_pg import get_pool
from kb.models import Source

log = logging.getLogger(__name__)


def list_sources(
    *,
    source_type: str | None = None,
    tag: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Source]:
    sql = """
        SELECT
          s.id, s.url, s.title, s.source_type, s.notes, s.chunk_count,
          s.markdown_path, s.ingested_at, s.metadata,
          COALESCE(
            ARRAY_AGG(t.name) FILTER (WHERE t.name IS NOT NULL),
            '{}'
          ) AS tags
        FROM sources s
        LEFT JOIN source_tags st ON st.source_id = s.id
        LEFT JOIN tags t ON t.id = st.tag_id
        WHERE (%(source_type)s::text IS NULL OR s.source_type = %(source_type)s)
          AND (
            %(tag)s::text IS NULL
            OR s.id IN (
              SELECT st2.source_id
              FROM source_tags st2
              JOIN tags t2 ON t2.id = st2.tag_id
              WHERE t2.name = %(tag)s
            )
          )
        GROUP BY s.id
        ORDER BY s.ingested_at DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """
    params = {
        "source_type": source_type,
        "tag": tag,
        "limit": limit,
        "offset": offset,
    }
    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [Source(**row) for row in cur.fetchall()]


def delete_source(source_id: UUID) -> bool:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT markdown_path FROM sources WHERE id = %s", (str(source_id),))
        row = cur.fetchone()
        if row is None:
            log.warning("Source not found: %s", source_id)
            return False

        markdown_path = row[0]
        cur.execute("DELETE FROM sources WHERE id = %s", (str(source_id),))

    if markdown_path:
        full_path = settings.kb_storage_path / markdown_path
        if full_path.exists():
            full_path.unlink()
            log.info("Deleted markdown: %s", full_path)

    log.info("Deleted source: %s", source_id)
    return True
