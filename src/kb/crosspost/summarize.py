"""Isolated summary generation + Slack cross-post.

IMPORTANT: Untrusted page content is summarized here in isolation and never
enters the agent's conversation loop.
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from kb.config import settings
from kb.ingest.llm import generate

log = logging.getLogger(__name__)


def generate_summary(title: str, content: str, url: str | None = None) -> str:
    """Generate a clean summary of ingested content."""
    prompt = (
        "Write a concise 2-3 sentence summary of the following content. "
        "Focus on the key takeaway.\n\n"
        f"Title: {title}\n\n"
        f"Content:\n{content[:3000]}\n\n"
        "Summary:"
    )
    summary = generate(prompt)

    # Clean the URL if present
    clean_url = strip_tracking_params(url) if url else None

    parts = [f"*{title}*", summary]
    if clean_url:
        parts.append(clean_url)

    return "\n\n".join(parts)


def post_to_slack(summary: str) -> bool:
    """Post a summary to the cross-post channel."""
    if not settings.slack_bot_token or not settings.slack_crosspost_channel_id:
        log.warning(
            "Cross-post not configured (missing token or channel)"
        )
        return False

    try:
        from slack_sdk import WebClient

        client = WebClient(token=settings.slack_bot_token)
        client.chat_postMessage(
            channel=settings.slack_crosspost_channel_id,
            text=summary,
        )
        log.info("Cross-posted to %s", settings.slack_crosspost_channel_id)
        return True
    except Exception as e:
        log.error("Cross-post failed: %s", e)
        return False


def crosspost(title: str, content: str, url: str | None = None) -> bool:
    """Generate summary and post to cross-post channel."""
    summary = generate_summary(title, content, url)
    return post_to_slack(summary)


# --- URL cleaning ---

# Common tracking parameters to strip
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid", "gclsrc",
    "mc_cid", "mc_eid", "mkt_tok",
    "_hsenc", "_hsmi", "hsCtaTracking",
}


def strip_tracking_params(url: str) -> str:
    """Remove UTM and other tracking parameters from a URL."""
    if not url:
        return url

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=False)

    # Filter out tracking params
    cleaned = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}

    # Rebuild URL
    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))
