"""Ingestion pipeline orchestrator.

Flow: validate -> fetch -> sanitize -> chunk -> embed -> tag -> store
"""

from __future__ import annotations

import logging

from kb.ingest.chunker import chunk_text
from kb.ingest.embeddings import embed_batch
from kb.ingest.fetchers import FetchResult, fetch_pdf_bytes, fetch_url
from kb.ingest.llm import generate
from kb.ingest.sanitize import sanitize
from kb.ingest.storage import store_chunks, store_source, store_tags, write_markdown
from kb.ingest.tagger import generate_tags
from kb.models import IngestResult, SourceType

log = logging.getLogger(__name__)


def ingest_url(url: str, notes: str | None = None) -> IngestResult:
    """Ingest a URL with optional user commentary.

    1. Chunk/embed commentary (content_type='commentary')
    2. Fetch URL content
    3. Sanitize fetched content
    4. For YouTube: LLM-summarize transcript, then chunk/embed summary
       For others: chunk/embed fetched text directly
    5. Tag from both streams (commentary weighted higher)
    6. Store everything
    """
    log.info("Ingesting URL: %s", url)

    # Fetch the URL content
    fetch_result = fetch_url(url)
    log.info("Fetched: %s (%s)", fetch_result.title, fetch_result.source_type)

    return _process(
        fetch_result=fetch_result,
        url=url,
        notes=notes,
    )


def ingest_pdf(data: bytes, filename: str, notes: str | None = None) -> IngestResult:
    """Ingest a PDF from raw bytes (e.g., Slack file upload)."""
    log.info("Ingesting PDF: %s", filename)

    fetch_result = fetch_pdf_bytes(data, filename)

    return _process(
        fetch_result=fetch_result,
        url=None,
        notes=notes,
    )


def ingest_document(text: str, title: str, notes: str | None = None) -> IngestResult:
    """Ingest raw text directly (no URL fetch)."""
    log.info("Ingesting document: %s", title)

    fetch_result = FetchResult(
        text=text,
        title=title,
        source_type="document",
    )

    return _process(
        fetch_result=fetch_result,
        url=None,
        notes=notes,
    )


def _process(
    *,
    fetch_result: FetchResult,
    url: str | None,
    notes: str | None,
) -> IngestResult:
    """Core processing: sanitize, chunk, embed, tag, store."""

    all_chunks: list[str] = []
    all_embeddings: list[list[float]] = []
    all_content_types: list[str] = []

    # --- Commentary ---
    if notes and notes.strip():
        log.info("Processing commentary...")
        commentary_chunks = chunk_text(notes)
        if commentary_chunks:
            commentary_embeddings = embed_batch(commentary_chunks)
            all_chunks.extend(commentary_chunks)
            all_embeddings.extend(commentary_embeddings)
            all_content_types.extend(["commentary"] * len(commentary_chunks))

    # --- Reference content ---
    ref_text = fetch_result.text

    # Sanitize fetched content
    san_result = sanitize(ref_text)
    if not san_result.is_clean:
        log.warning("Sanitization flags on %s: %s", url or fetch_result.title, san_result.flags)
    ref_text = san_result.text

    # YouTube: summarize transcript instead of chunking raw
    if fetch_result.source_type == "youtube":
        log.info("Summarizing YouTube transcript...")
        ref_text = _summarize_transcript(ref_text, fetch_result.title)

    log.info("Processing reference content...")
    ref_chunks = chunk_text(ref_text)
    if ref_chunks:
        ref_embeddings = embed_batch(ref_chunks)
        all_chunks.extend(ref_chunks)
        all_embeddings.extend(ref_embeddings)
        all_content_types.extend(["reference"] * len(ref_chunks))

    # --- Tagging ---
    log.info("Generating tags...")
    tags = generate_tags(
        commentary=notes,
        reference_text=ref_text[:3000],
    )
    log.info("Tags: %s", tags)

    # --- Write markdown to disk ---
    markdown_path = write_markdown(
        title=fetch_result.title,
        content=ref_text,
        notes=notes,
    )

    # --- Store to Supabase ---
    total_chunks = len(all_chunks)
    source_id = store_source(
        url=url,
        title=fetch_result.title,
        source_type=fetch_result.source_type,
        notes=notes,
        chunk_count=total_chunks,
        markdown_path=markdown_path,
        metadata=fetch_result.metadata,
    )

    # Store chunks in groups by content type
    commentary_count = all_content_types.count("commentary")
    if commentary_count > 0:
        store_chunks(
            source_id,
            all_chunks[:commentary_count],
            all_embeddings[:commentary_count],
            "commentary",
        )
    if commentary_count < total_chunks:
        store_chunks(
            source_id,
            all_chunks[commentary_count:],
            all_embeddings[commentary_count:],
            "reference",
        )

    # Store tags
    store_tags(source_id, tags)

    log.info("Stored: %s (%d chunks, %d tags)", fetch_result.title, total_chunks, len(tags))

    return IngestResult(
        source_id=source_id,
        title=fetch_result.title,
        source_type=SourceType(fetch_result.source_type),
        tags=tags,
        chunk_count=total_chunks,
        markdown_path=markdown_path,
    )


def _summarize_transcript(transcript: str, title: str) -> str:
    """Summarize a YouTube transcript via LLM."""
    # Truncate very long transcripts to stay within context limits
    truncated = transcript[:8000]

    prompt = (
        f"Summarize the following YouTube video transcript. The video is titled: {title}\n\n"
        "Provide a comprehensive summary that captures the key points, arguments, "
        "and conclusions. Organize by topic if appropriate.\n\n"
        f"Transcript:\n{truncated}\n\n"
        "Summary:"
    )

    return generate(prompt)
