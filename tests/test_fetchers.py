"""Tests for URL type detection and YouTube ID extraction."""

from kb.ingest.fetchers import _extract_youtube_id, detect_source_type


def test_detect_youtube():
    assert detect_source_type("https://www.youtube.com/watch?v=abc123def45") == "youtube"
    assert detect_source_type("https://youtu.be/abc123def45") == "youtube"
    assert detect_source_type("https://m.youtube.com/watch?v=abc123def45") == "youtube"


def test_detect_tweet():
    assert detect_source_type("https://twitter.com/user/status/123") == "tweet"
    assert detect_source_type("https://x.com/user/status/123") == "tweet"


def test_detect_pdf():
    assert detect_source_type("https://example.com/paper.pdf") == "pdf"
    assert detect_source_type("https://example.com/doc.PDF") == "pdf"


def test_detect_article():
    assert detect_source_type("https://example.com/blog/post") == "article"
    assert detect_source_type("https://medium.com/@user/some-title") == "article"


def test_extract_youtube_id():
    assert _extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_youtube_id("https://example.com/not-youtube") is None
