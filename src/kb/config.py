"""Configuration via pydantic-settings. All env vars defined here."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(str, Enum):
    ollama = "ollama"
    anthropic = "anthropic"
    openrouter = "openrouter"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database backend selection (supabase | postgres) ---
    db_backend: Literal["supabase", "postgres"] = "supabase"

    # --- Supabase (used when db_backend == "supabase") ---
    supabase_url: str
    supabase_key: str

    # --- Local PostgreSQL (used when db_backend == "postgres") ---
    database_url: Optional[str] = None

    # --- Ollama ---
    ollama_host: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_llm_model: str = "llama3.2"

    # --- Provider selection ---
    embed_provider: Provider = Provider.ollama
    llm_provider: Provider = Provider.ollama

    # --- Anthropic ---
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_embed_model: str = "voyage-3"

    # --- OpenRouter ---
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "deepseek/deepseek-v3.2"
    openrouter_embed_model: str = ""

    # --- Storage ---
    kb_storage_path: Path = Path("~/kb-store")

    # --- Slack ---
    slack_bot_token: Optional[str] = None
    slack_app_token: Optional[str] = None
    slack_channel_id: Optional[str] = None
    slack_crosspost_channel_id: Optional[str] = None

    # --- Sanitization ---
    sanitize_llm_scan: bool = False

    @field_validator("kb_storage_path", mode="before")
    @classmethod
    def expand_home(cls, v: str | Path) -> Path:
        return Path(v).expanduser()


settings = Settings()  # type: ignore[call-arg]
