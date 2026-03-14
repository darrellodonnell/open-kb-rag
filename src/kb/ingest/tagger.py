"""Auto-tagging via LLM — commentary weighted higher than reference content."""

from __future__ import annotations

import json
import re

from kb.ingest.llm import generate


def generate_tags(
    commentary: str | None = None,
    reference_text: str | None = None,
    max_tags: int = 8,
) -> list[str]:
    """Generate tags from commentary and/or reference text.

    Commentary is weighted higher in the prompt — it represents the user's
    own framing of the content and should drive tag selection.
    """
    parts: list[str] = []

    if commentary and commentary.strip():
        parts.append(
            "## User Commentary (PRIMARY — this is the user's own perspective; "
            "weight this heavily for tag selection):\n"
            f"{commentary.strip()}"
        )

    if reference_text and reference_text.strip():
        # Truncate reference to avoid overwhelming the prompt
        ref = reference_text.strip()[:3000]
        parts.append(
            "## Reference Content (SECONDARY — use this for additional context, "
            "but defer to the user's commentary for tag direction):\n"
            f"{ref}"
        )

    if not parts:
        return []

    content = "\n\n".join(parts)

    prompt = (
        "Generate up to {max_tags} descriptive tags for the following content. "
        "Tags should be lowercase, hyphenated (e.g., 'machine-learning', not "
        "'Machine Learning'), and capture the key topics and themes.\n\n"
        "IMPORTANT: The user's commentary section (if present) should be the "
        "primary driver of tag selection. Reference content provides supporting "
        "context only.\n\n"
        f"{content}\n\n"
        f"Return ONLY a JSON array of up to {max_tags} tag strings. "
        "Example: [\"digital-identity\", \"verifiable-credentials\", \"trust-frameworks\"]\n"
        "JSON array:"
    )

    response = generate(prompt)
    return _parse_tags(response, max_tags)


def _parse_tags(response: str, max_tags: int) -> list[str]:
    """Parse LLM response into a list of normalized tag strings."""
    # Try to extract JSON array from the response
    # Handle cases where LLM wraps in markdown code blocks
    cleaned = response.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        tags = json.loads(cleaned)
        if isinstance(tags, list):
            return _normalize_tags(tags, max_tags)
    except json.JSONDecodeError:
        pass

    # Fallback: try to find a JSON array anywhere in the response
    match = re.search(r"\[.*?\]", response, re.DOTALL)
    if match:
        try:
            tags = json.loads(match.group())
            if isinstance(tags, list):
                return _normalize_tags(tags, max_tags)
        except json.JSONDecodeError:
            pass

    # Last resort: split on commas/newlines and clean up
    raw = re.split(r"[,\n]", response)
    tags = [t.strip().strip("\"'`-# ") for t in raw if t.strip()]
    return _normalize_tags(tags, max_tags)


def _normalize_tags(tags: list, max_tags: int) -> list[str]:
    """Normalize tags: lowercase, hyphenated, deduplicated."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        normalized = tag.lower().strip().replace(" ", "-")
        # Remove non-alphanumeric except hyphens
        normalized = re.sub(r"[^a-z0-9-]", "", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
        if len(result) >= max_tags:
            break
    return result
