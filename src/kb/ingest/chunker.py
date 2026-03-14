"""Hybrid paragraph-based chunker targeting ~512 tokens per chunk."""

from __future__ import annotations

import re

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")

TARGET_TOKENS = 512
MAX_TOKENS = 768  # hard upper limit before forced split


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return len(_enc.encode(text))


def chunk_text(text: str, target: int = TARGET_TOKENS) -> list[str]:
    """Split text into chunks of approximately `target` tokens.

    Strategy:
    1. Split on double newlines (paragraphs).
    2. Merge small consecutive paragraphs up to the target.
    3. Split oversized paragraphs on sentence boundaries.
    """
    paragraphs = _split_paragraphs(text)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)

        # Oversized paragraph — split on sentences first
        if para_tokens > MAX_TOKENS:
            # Flush current buffer
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0
            # Split the large paragraph into sentence-based chunks
            chunks.extend(_split_sentences(para, target))
            continue

        # Would adding this paragraph exceed target?
        if current_tokens + para_tokens > target and current:
            chunks.append("\n\n".join(current))
            current = []
            current_tokens = 0

        current.append(para)
        current_tokens += para_tokens

    # Flush remaining
    if current:
        chunks.append("\n\n".join(current))

    return [c.strip() for c in chunks if c.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """Split text on double newlines, filtering empty results."""
    parts = re.split(r"\n{2,}", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str, target: int) -> list[str]:
    """Split a large block on sentence boundaries, targeting `target` tokens."""
    # Split on sentence-ending punctuation followed by space or newline
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sent_tokens = count_tokens(sentence)

        # Single sentence exceeds target — include it as its own chunk
        if sent_tokens > target:
            if current:
                chunks.append(" ".join(current))
                current = []
                current_tokens = 0
            chunks.append(sentence)
            continue

        if current_tokens + sent_tokens > target and current:
            chunks.append(" ".join(current))
            current = []
            current_tokens = 0

        current.append(sentence)
        current_tokens += sent_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks
