"""Test configuration — set required env vars before settings loads."""

import os

# Set minimum required env vars for tests (before any kb imports)
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
