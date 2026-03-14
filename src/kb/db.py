"""Supabase client initialization."""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from kb.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return a cached Supabase client."""
    return create_client(settings.supabase_url, settings.supabase_key)
