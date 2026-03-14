"""Slack message handlers — parse URLs, PDFs, commentary, call pipeline."""

from __future__ import annotations

import logging
import re

import httpx

from kb.config import settings
from kb.ingest.pipeline import ingest_pdf, ingest_url
from kb.models import IngestResult

log = logging.getLogger(__name__)

# URL regex — matches http(s) URLs in message text
_URL_PATTERN = re.compile(r"<(https?://[^|>]+)(?:\|[^>]*)?>")


def handle_message(event: dict, say) -> None:
    """Handle an incoming Slack message.

    Extracts URLs and file uploads, captures surrounding text as commentary,
    and passes everything to the ingestion pipeline.
    """
    text = event.get("text", "")
    files = event.get("files", [])

    # Extract URLs from Slack's <url|label> format
    urls = _URL_PATTERN.findall(text)

    # Extract commentary (message text minus the URLs)
    commentary = _URL_PATTERN.sub("", text).strip()
    if not commentary:
        commentary = None

    results: list[IngestResult] = []

    # Process URLs
    for url in urls:
        try:
            result = ingest_url(url, notes=commentary)
            results.append(result)
        except Exception as e:
            log.error("Failed to ingest URL %s: %s", url, e)
            say(f"Failed to ingest {url}: {e}")

    # Process PDF file uploads
    for file_info in files:
        if file_info.get("mimetype") == "application/pdf":
            try:
                result = _handle_pdf_upload(file_info, commentary)
                if result:
                    results.append(result)
            except Exception as e:
                log.error("Failed to ingest PDF %s: %s", file_info.get("name"), e)
                say(f"Failed to ingest PDF {file_info.get('name')}: {e}")

    # Reply with confirmation
    if results:
        for result in results:
            tags_str = ", ".join(result.tags) if result.tags else "none"
            say(
                f"Ingested: *{result.title}*\n"
                f"Type: {result.source_type.value} | "
                f"Chunks: {result.chunk_count} | "
                f"Tags: {tags_str}"
            )
    elif not urls and not files:
        # Message had no URLs or files — ignore silently
        pass


def _handle_pdf_upload(file_info: dict, commentary: str | None) -> IngestResult | None:
    """Download and ingest a PDF file from Slack."""
    url_private = file_info.get("url_private")
    filename = file_info.get("name", "upload.pdf")

    if not url_private:
        log.warning("PDF file has no url_private: %s", filename)
        return None

    # Download the file using the bot token
    resp = httpx.get(
        url_private,
        headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()

    return ingest_pdf(resp.content, filename, notes=commentary)
