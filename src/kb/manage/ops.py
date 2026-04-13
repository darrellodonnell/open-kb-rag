"""Management operations — list, delete, bulk ingest."""

from __future__ import annotations

import logging
from uuid import UUID

from kb.config import settings
from kb.db import get_client
from kb.models import IngestResult, Source

log = logging.getLogger(__name__)


def list_sources(
    *,
    source_type: str | None = None,
    tag: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Source]:
    """List sources with optional filters."""
    if settings.db_backend == "postgres":
        from kb.manage.ops_pg import list_sources as _pg

        return _pg(source_type=source_type, tag=tag, limit=limit, offset=offset)

    client = get_client()

    query = client.table("sources").select(
        "*, source_tags(tag_id, tags(name))"
    ).order("ingested_at", desc=True).range(offset, offset + limit - 1)

    if source_type:
        query = query.eq("source_type", source_type)

    result = query.execute()

    sources = []
    for row in result.data:
        # Extract tag names from the nested join
        tag_names = []
        for st in row.pop("source_tags", []):
            tag_info = st.get("tags")
            if tag_info and "name" in tag_info:
                tag_names.append(tag_info["name"])

        # Apply tag filter client-side (Supabase doesn't easily filter through joins)
        if tag and tag not in tag_names:
            continue

        sources.append(Source(**row, tags=tag_names))

    return sources


def delete_source(source_id: UUID) -> bool:
    """Delete a source and all its chunks/tags from DB. Also removes markdown from disk."""
    if settings.db_backend == "postgres":
        from kb.manage.ops_pg import delete_source as _pg

        return _pg(source_id)

    client = get_client()

    # Get the source to find the markdown path
    result = client.table("sources").select("markdown_path").eq("id", str(source_id)).execute()
    if not result.data:
        log.warning("Source not found: %s", source_id)
        return False

    markdown_path = result.data[0].get("markdown_path")

    # Delete from DB (chunks and source_tags cascade)
    client.table("sources").delete().eq("id", str(source_id)).execute()

    # Delete markdown file from disk
    if markdown_path:
        full_path = settings.kb_storage_path / markdown_path
        if full_path.exists():
            full_path.unlink()
            log.info("Deleted markdown: %s", full_path)

    log.info("Deleted source: %s", source_id)
    return True


def bulk_ingest(urls: list[str], notes: str | None = None) -> list[IngestResult]:
    """Ingest multiple URLs sequentially."""
    from kb.ingest.pipeline import ingest_url

    results: list[IngestResult] = []
    for url in urls:
        try:
            result = ingest_url(url.strip(), notes=notes)
            results.append(result)
            log.info("Ingested: %s", url)
        except Exception as e:
            log.error("Failed to ingest %s: %s", url, e)

    return results


def bulk_ingest_from_file(filepath: str, notes: str | None = None) -> list[IngestResult]:
    """Read URLs from a file (one per line) and ingest them."""
    from pathlib import Path

    path = Path(filepath).expanduser()
    lines = path.read_text().splitlines()
    urls = [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return bulk_ingest(urls, notes=notes)
