"""Tests for URL cleaning in crosspost module."""

from kb.crosspost.summarize import strip_tracking_params


def test_strip_utm_params():
    url = "https://example.com/article?utm_source=twitter&utm_medium=social&id=42"
    cleaned = strip_tracking_params(url)
    assert "utm_source" not in cleaned
    assert "utm_medium" not in cleaned
    assert "id=42" in cleaned


def test_strip_fbclid():
    url = "https://example.com/page?fbclid=abc123&real_param=value"
    cleaned = strip_tracking_params(url)
    assert "fbclid" not in cleaned
    assert "real_param=value" in cleaned


def test_no_params_unchanged():
    url = "https://example.com/article"
    assert strip_tracking_params(url) == url


def test_empty_string():
    assert strip_tracking_params("") == ""


def test_only_tracking_params():
    url = "https://example.com/page?utm_source=x&utm_medium=y"
    cleaned = strip_tracking_params(url)
    assert "utm_source" not in cleaned
    assert cleaned.startswith("https://example.com/page")
