"""Tests for the hybrid paragraph-based chunker."""

from kb.ingest.chunker import chunk_text, count_tokens


def test_count_tokens():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0


def test_single_small_paragraph():
    text = "This is a short paragraph."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_multiple_small_paragraphs_merge():
    """Small paragraphs should be merged into one chunk."""
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = chunk_text(text)
    # All three should merge into one chunk (well under 512 tokens)
    assert len(chunks) == 1
    assert "First paragraph." in chunks[0]
    assert "Third paragraph." in chunks[0]


def test_large_paragraph_splits():
    """A paragraph exceeding MAX_TOKENS should be split on sentences."""
    # Create a paragraph with many sentences
    sentences = ["This is sentence number {i}." for i in range(200)]
    text = " ".join(sentences)
    chunks = chunk_text(text)
    assert len(chunks) > 1
    # Each chunk should be non-empty
    for chunk in chunks:
        assert len(chunk) > 0


def test_empty_input():
    assert chunk_text("") == []
    assert chunk_text("   ") == []
    assert chunk_text("\n\n\n") == []


def test_preserves_content():
    """All content should be preserved across chunks."""
    text = "Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph."
    chunks = chunk_text(text)
    combined = " ".join(chunks)
    assert "Alpha" in combined
    assert "Beta" in combined
    assert "Gamma" in combined
