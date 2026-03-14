"""Test configuration — set required env vars before settings loads."""

import os

# Set minimum required env vars for tests (before any kb imports)
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
