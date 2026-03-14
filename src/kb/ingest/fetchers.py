"""Content fetchers — per-type URL handling."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


@dataclass
class FetchResult:
    """Result of fetching content from a URL."""

    text: str
    title: str
    source_type: str
    metadata: dict = field(default_factory=dict)


def detect_source_type(url: str) -> str:
    """Detect source type from URL pattern."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # YouTube
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        return "youtube"
    if host == "youtu.be":
        return "youtube"

    # Twitter/X
    if host in ("twitter.com", "www.twitter.com", "x.com", "www.x.com"):
        return "tweet"

    # PDF (by extension)
    if parsed.path.lower().endswith(".pdf"):
        return "pdf"

    # Default: article
    return "article"


def fetch_url(url: str) -> FetchResult:
    """Fetch content from a URL using the appropriate method."""
    # Validate URL scheme
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}. Only http/https allowed.")

    source_type = detect_source_type(url)

    if source_type == "youtube":
        return _fetch_youtube(url)
    elif source_type == "tweet":
        return _fetch_tweet(url)
    elif source_type == "pdf":
        return _fetch_pdf_from_url(url)
    else:
        return _fetch_article(url)


def fetch_pdf_bytes(data: bytes, filename: str = "upload.pdf") -> FetchResult:
    """Extract text from PDF bytes (for Slack file uploads)."""
    import pymupdf

    doc = pymupdf.open(stream=data, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()

    text = "\n\n".join(pages)
    title = filename.rsplit(".", 1)[0] if "." in filename else filename

    return FetchResult(
        text=text,
        title=title,
        source_type="pdf",
        metadata={"page_count": len(pages), "filename": filename},
    )


# --- PDF from URL ---


def _fetch_pdf_from_url(url: str) -> FetchResult:
    """Download a PDF from a URL and extract text."""
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return fetch_pdf_bytes(resp.content, filename=url.rsplit("/", 1)[-1])


# --- Article (trafilatura) ---


def _fetch_article(url: str) -> FetchResult:
    import trafilatura

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise RuntimeError(f"Failed to download: {url}")

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
    if not text:
        raise RuntimeError(f"Failed to extract text from: {url}")

    metadata = trafilatura.extract(
        downloaded,
        output_format="json",
        include_comments=False,
    )
    title = "Untitled"
    if metadata:
        import json

        meta = json.loads(metadata)
        title = meta.get("title", "Untitled")

    # Fallback: extract <title> from raw HTML if trafilatura missed it
    if title == "Untitled":
        title = _extract_html_title(downloaded) or "Untitled"

    return FetchResult(
        text=text,
        title=title,
        source_type="article",
        metadata={"url": url},
    )


# --- YouTube (transcript) ---


def _fetch_youtube(url: str) -> FetchResult:
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = _extract_youtube_id(url)
    if not video_id:
        raise ValueError(f"Could not extract YouTube video ID from: {url}")

    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)

    # Combine transcript segments into full text
    full_text = " ".join(segment.text for segment in transcript)

    # Get video title via oEmbed (no API key needed)
    title = _get_youtube_title(url)

    return FetchResult(
        text=full_text,
        title=title,
        source_type="youtube",
        metadata={"video_id": video_id, "url": url},
    )


def _extract_youtube_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|/v/)([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _extract_html_title(html: str) -> str | None:
    """Extract <title> from raw HTML as a fallback."""
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # Clean common suffixes like " - Wikipedia"
        for suffix in [" - Wikipedia", " | "]:
            if suffix in title:
                title = title.split(suffix)[0].strip()
        return title if title else None
    return None


def _get_youtube_title(url: str) -> str:
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("title", "YouTube Video")
    except Exception:
        return "YouTube Video"


# --- Tweet (FxTwitter API) ---


def _fetch_tweet(url: str) -> FetchResult:
    """Fetch tweet via embed APIs (no auth required).

    Tries multiple services in order: FxTwitter, FixTweet/VxTwitter.
    Falls back to oEmbed for at least the text.
    """
    parsed = urlparse(url)
    path = parsed.path

    # Try FxTwitter first
    services = [
        f"https://api.fxtwitter.com{path}",
        f"https://api.vxtwitter.com{path}",
    ]

    for api_url in services:
        try:
            resp = httpx.get(api_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            tweet = data.get("tweet", {})
            text = tweet.get("text", "")
            if not text:
                continue
            author = tweet.get("author", {}).get("name", "Unknown")
            handle = tweet.get("author", {}).get("screen_name", "")

            title = (
                f"@{handle}: {text[:80]}..."
                if len(text) > 80
                else f"@{handle}: {text}"
            )
            return FetchResult(
                text=text,
                title=title,
                source_type="tweet",
                metadata={"author": author, "handle": handle, "url": url},
            )
        except Exception:
            continue

    # Fallback: use publish.twitter.com oEmbed (usually works)
    try:
        return _fetch_tweet_oembed(url)
    except Exception:
        raise RuntimeError(
            f"Could not fetch tweet from {url}. "
            "All services failed (FxTwitter, VxTwitter, Twitter oEmbed). "
            "The tweet may be deleted, protected, or the services may be down. "
            "You can retry later."
        )


def _fetch_tweet_oembed(url: str) -> FetchResult:
    """Fallback: fetch tweet text via Twitter's oEmbed endpoint."""
    # Normalize URL to twitter.com for oEmbed
    normalized = url.replace("x.com", "twitter.com")
    resp = httpx.get(
        "https://publish.twitter.com/oembed",
        params={"url": normalized, "omit_script": "true"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    # oEmbed returns HTML — strip tags to get plain text
    import re as _re

    html = data.get("html", "")
    text = _re.sub(r"<[^>]+>", "", html).strip()
    author = data.get("author_name", "Unknown")

    title = f"{author}: {text[:80]}..." if len(text) > 80 else f"{author}: {text}"
    return FetchResult(
        text=text,
        title=title,
        source_type="tweet",
        metadata={"author": author, "url": url},
    )
