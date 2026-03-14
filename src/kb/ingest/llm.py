"""LLM generation — configurable provider (Ollama, Anthropic, OpenRouter)."""

from __future__ import annotations

import httpx
import ollama as ollama_client

from kb.config import Provider, settings


def generate(prompt: str, system: str | None = None) -> str:
    """Generate text from the configured LLM provider."""
    provider = settings.llm_provider
    if provider == Provider.ollama:
        return _generate_ollama(prompt, system)
    elif provider == Provider.anthropic:
        return _generate_anthropic(prompt, system)
    elif provider == Provider.openrouter:
        return _generate_openrouter(prompt, system)
    raise ValueError(f"Unknown LLM provider: {provider}")


# --- Ollama ---


def _generate_ollama(prompt: str, system: str | None) -> str:
    resp = ollama_client.generate(
        model=settings.ollama_llm_model,
        prompt=prompt,
        system=system or "",
        options={"temperature": 0.3},
    )
    return resp["response"]


# --- Anthropic ---


def _generate_anthropic(prompt: str, system: str | None) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": prompt}]
    resp = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=system or "",
        messages=messages,
    )
    return resp.content[0].text


# --- OpenRouter ---


def _generate_openrouter(prompt: str, system: str | None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openrouter_model,
            "messages": messages,
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
