"""Tests for the tag parser/normalizer (no LLM calls)."""

from kb.ingest.tagger import _normalize_tags, _parse_tags


def test_parse_json_array():
    response = '["machine-learning", "neural-networks", "deep-learning"]'
    tags = _parse_tags(response, max_tags=8)
    assert tags == ["machine-learning", "neural-networks", "deep-learning"]


def test_parse_markdown_wrapped():
    response = '```json\n["ai", "robotics"]\n```'
    tags = _parse_tags(response, max_tags=8)
    assert tags == ["ai", "robotics"]


def test_parse_fallback_comma_separated():
    response = "machine learning, neural networks, deep learning"
    tags = _parse_tags(response, max_tags=8)
    assert len(tags) == 3
    assert "machine-learning" in tags


def test_normalize_deduplicates():
    tags = _normalize_tags(["AI", "ai", "Ai"], max_tags=8)
    assert tags == ["ai"]


def test_normalize_hyphenates_spaces():
    tags = _normalize_tags(["machine learning", "deep learning"], max_tags=8)
    assert tags == ["machine-learning", "deep-learning"]


def test_normalize_strips_special_chars():
    tags = _normalize_tags(["c++", "node.js", "#hashtag"], max_tags=8)
    assert "c" in tags
    assert "nodejs" in tags
    assert "hashtag" in tags


def test_normalize_respects_max():
    tags = _normalize_tags(["a", "b", "c", "d", "e"], max_tags=3)
    assert len(tags) == 3


def test_normalize_skips_non_strings():
    tags = _normalize_tags(["valid", 123, None, "also-valid"], max_tags=8)
    assert tags == ["valid", "also-valid"]
