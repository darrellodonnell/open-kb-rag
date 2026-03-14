"""Startup checks: verify DB connection and storage path."""

from __future__ import annotations

import sys

from kb.config import settings


def check_storage_path() -> bool:
    """Verify the KB storage directory exists and is writable."""
    path = settings.kb_storage_path
    if not path.exists():
        print(f"  FAIL: Storage path does not exist: {path}")
        print(f"        Run: mkdir -p {path}")
        return False
    if not path.is_dir():
        print(f"  FAIL: Storage path is not a directory: {path}")
        return False
    # Check writable by attempting to create a temp file
    test_file = path / ".preflight_check"
    try:
        test_file.touch()
        test_file.unlink()
    except OSError as e:
        print(f"  FAIL: Storage path is not writable: {path} ({e})")
        return False
    print(f"  OK: Storage path: {path}")
    return True


def check_supabase() -> bool:
    """Verify Supabase connection by querying the sources table."""
    try:
        from kb.db import get_client

        client = get_client()
        # Simple query to verify connectivity — will fail if table doesn't exist
        client.table("sources").select("id").limit(1).execute()
        print("  OK: Supabase connection")
        return True
    except Exception as e:
        print(f"  FAIL: Supabase connection: {e}")
        return False


def check_ollama() -> bool:
    """Verify Ollama is reachable."""
    try:
        import httpx

        resp = httpx.get(f"{settings.ollama_host}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        print(f"  OK: Ollama reachable — {len(models)} model(s) available")
        return True
    except Exception as e:
        print(f"  FAIL: Ollama at {settings.ollama_host}: {e}")
        return False


def run_all() -> bool:
    """Run all preflight checks. Returns True if all pass."""
    print("Preflight checks:")
    results = [
        check_storage_path(),
        check_supabase(),
        check_ollama(),
    ]
    passed = all(results)
    print()
    if passed:
        print("All checks passed.")
    else:
        print(f"{results.count(False)} check(s) failed.")
    return passed


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
