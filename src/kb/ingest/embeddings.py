"""Embedding generation — configurable provider (Ollama, Anthropic, OpenRouter)."""

from __future__ import annotations

import httpx
import ollama as ollama_client

from kb.config import Provider, settings


def embed(text: str) -> list[float]:
    """Generate an embedding for a single text string."""
    provider = settings.embed_provider
    if provider == Provider.ollama:
        return _embed_ollama(text)
    elif provider == Provider.anthropic:
        return _embed_anthropic([text])[0]
    elif provider == Provider.openrouter:
        return _embed_openrouter([text])[0]
    raise ValueError(f"Unknown embed provider: {provider}")


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    if not texts:
        return []

    provider = settings.embed_provider
    if provider == Provider.ollama:
        return _embed_ollama_batch(texts, batch_size)
    elif provider == Provider.anthropic:
        return _embed_anthropic(texts)
    elif provider == Provider.openrouter:
        return _embed_openrouter(texts)
    raise ValueError(f"Unknown embed provider: {provider}")


# --- Ollama ---


def _embed_ollama(text: str) -> list[float]:
    resp = ollama_client.embed(model=settings.ollama_embed_model, input=text)
    return resp["embeddings"][0]


def _embed_ollama_batch(texts: list[str], batch_size: int) -> list[list[float]]:
    results: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = ollama_client.embed(model=settings.ollama_embed_model, input=batch)
        results.extend(resp["embeddings"])
    return results


# --- Anthropic (Voyage) ---


def _embed_anthropic(texts: list[str]) -> list[list[float]]:
    """Use Anthropic's Voyage embedding API."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    # Voyage embeddings via Anthropic's API
    resp = client.embeddings.create(
        model=settings.anthropic_embed_model,
        input=texts,
    )
    return [item.embedding for item in resp.data]


# --- OpenRouter ---


def _embed_openrouter(texts: list[str]) -> list[list[float]]:
    """Use OpenRouter embedding endpoint (OpenAI-compatible)."""
    resp = httpx.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openrouter_embed_model,
            "input": texts,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return [item["embedding"] for item in data["data"]]
