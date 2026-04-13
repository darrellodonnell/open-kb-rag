# Plan: Migrate Supabase → Local PostgreSQL

**Status:** Draft
**Date:** 2026-04-13
**Estimated effort:** 7–10 hours
**Target host:** `jones.quagga-chicken.ts.net` (Ubuntu VM on Tailnet — same host running `kb-slack.service` and `kb-mcp.service`)

---

## Goal

Replace the Supabase-hosted Postgres + pgvector with a local PostgreSQL instance running on the Ubuntu VM. All functionality (ingest, query, manage) stays identical; only the storage backend and client library change.

## Non-goals

- No change to embedding model (nomic-embed-text, 768 dims) or chunking logic.
- No change to Slack bot or MCP server interfaces.
- No migration to a different vector DB (e.g. Qdrant) — staying on Postgres + pgvector.
- No multi-user auth layer.

---

## Phase 1 — Provision local Postgres (Ubuntu VM, ~1–2h)

1. Install Postgres 16 + pgvector on the Ubuntu VM:
   ```bash
   sudo apt install postgresql-16 postgresql-16-pgvector
   ```
2. Create DB + role:
   ```sql
   CREATE ROLE kb WITH LOGIN PASSWORD '...';
   CREATE DATABASE kb OWNER kb;
   \c kb
   CREATE EXTENSION vector;
   ```
3. Configure `pg_hba.conf` to allow connections from `localhost` only (services run on the same host — no need to expose on Tailnet yet).
4. Apply `sql/init.sql` as the `kb` role — it already creates tables, indexes, HNSW, and the `search_chunks` function. The file is Supabase-agnostic; expect it to apply cleanly.
5. Verify: `\d chunks` shows `embedding vector(768)`; `SELECT proname FROM pg_proc WHERE proname = 'search_chunks'` returns one row.

**Exit criteria:** Can connect via `psql postgresql://kb@localhost/kb` and the schema is present.

---

## Phase 2 — Add psycopg driver, parallel to Supabase (~2h)

Keep Supabase working while building the local path, so rollback is just an env flag.

1. Add dependency in [pyproject.toml](pyproject.toml):
   ```
   "psycopg[binary,pool]>=3.2",
   ```
   Keep `supabase>=2.0` for now. Remove at the end of Phase 5.

2. Extend [src/kb/config.py](src/kb/config.py) to add:
   - `database_url: str | None = None` (Postgres DSN)
   - `db_backend: Literal["supabase", "postgres"] = "supabase"` (feature flag)

3. Create `src/kb/db_pg.py` with a `psycopg_pool.ConnectionPool` singleton mirroring the `@lru_cache` pattern in [src/kb/db.py](src/kb/db.py). Register the pgvector adapter (`pgvector.psycopg.register_vector`) on pool connections.

4. Add `pgvector>=0.3` to dependencies (provides the `Vector` type adapter for psycopg).

**Exit criteria:** `from kb.db_pg import get_pool; get_pool().connection()` works against the local DB.

---

## Phase 3 — Port each call site behind the flag (~3–4h)

Four files call Supabase. Each grows a `_pg` variant, and a small dispatcher picks based on `settings.db_backend`.

### 3a. [src/kb/ingest/storage.py](src/kb/ingest/storage.py)
Replace `.table("sources").insert(...)` / `.upsert(...)` / chunk batching with raw SQL:
- `INSERT INTO sources (...) VALUES (...) RETURNING id`
- `INSERT INTO chunks (source_id, chunk_index, content, content_type, token_count, embedding) VALUES %s` (use `psycopg.extras.execute_values` or `copy`)
- `INSERT INTO tags (name) VALUES (...) ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id`
- `INSERT INTO source_tags (source_id, tag_id) VALUES (...) ON CONFLICT DO NOTHING`

Wrap the source + chunks + tags work in a single transaction (Supabase did this implicitly across multiple HTTP calls — bad; native Postgres gives us atomicity for free).

### 3b. [src/kb/manage/ops.py](src/kb/manage/ops.py)
- `list_sources()` → `SELECT ... FROM sources ORDER BY ingested_at DESC`
- `delete_source(id)` → `DELETE FROM sources WHERE id = %s` (cascades to chunks/source_tags via the schema)

### 3c. [src/kb/query/engine.py](src/kb/query/engine.py)
Replace `client.rpc("search_chunks", params).execute()` with:
```python
cur.execute("SELECT * FROM search_chunks(%s, %s, %s, %s, %s)",
            (query_embedding, match_count, similarity_threshold, tags, source_type))
```
The PL/pgSQL function already exists in `sql/init.sql` — no porting needed.

### 3d. [src/kb/preflight.py](src/kb/preflight.py)
Replace `get_client().table("sources").select("id").limit(1)` with `SELECT 1 FROM sources LIMIT 1`.

**Exit criteria:** With `DB_BACKEND=postgres`, all three entry points (Slack ingest, MCP query, CLI manage) work against the local DB. Tests pass.

---

## Phase 4 — Data migration (~1h)

One-time copy from Supabase → local.

1. On the Mac dev box, `pg_dump` the Supabase project using its connection string:
   ```bash
   pg_dump --no-owner --no-acl --data-only \
     --table=sources --table=chunks --table=tags --table=source_tags \
     "$SUPABASE_PG_URL" > kb-data.sql
   ```
2. `psql postgresql://kb@vm-host/kb < kb-data.sql` (over Tailnet or scp-then-local).
3. Verify row counts match between Supabase and local for all four tables.
4. Re-sync the `markdown_path` references if the storage root on the VM differs (`KB_STORAGE_PATH`). Markdown files themselves may already be on the VM — confirm before cutover.

**Exit criteria:** `SELECT count(*) FROM chunks` matches Supabase; a sample query returns identical top-3 results on both backends.

---

## Phase 5 — Cutover and cleanup (~1h)

1. Flip `DB_BACKEND=postgres` in `.env.local` on the VM. Restart `kb-slack.service` and `kb-mcp.service`.
2. Smoke test: ingest one URL via Slack; query it via MCP; delete it via CLI.
3. Remove Supabase:
   - Drop `supabase>=2.0` from [pyproject.toml](pyproject.toml).
   - Delete [src/kb/db.py](src/kb/db.py) (Supabase client) and rename `db_pg.py` → `db.py`.
   - Remove the `db_backend` flag and the dispatcher; make Postgres the only path.
   - Remove `supabase_url` / `supabase_key` from config and `.env.example`.
4. Pause the Supabase project (keep it around for 2 weeks as a rollback safety net, then delete).

**Exit criteria:** `grep -r supabase src/` returns nothing. Services healthy for 48h.

---

## Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Row-count mismatch after `pg_dump` (sequence out of sync) | `SELECT setval` on all `*_id_seq` after restore |
| pgvector version skew between Supabase and apt package | Check `SELECT extversion FROM pg_extension WHERE extname='vector'` on both; if Supabase is newer, build pgvector from source |
| HNSW index build takes minutes on large chunk table | Acceptable one-time cost; run during a quiet window |
| Vector similarity drifts slightly (float rounding) | Spot-check top-K of 5 queries; tolerance is fine for semantic search — ranking stability matters more than exact scores |
| VM disk fills up | Check `df -h` on the VM; Postgres + markdown store should be well under 10GB for a personal KB |

---

## Decisions

1. **Backups** — nightly `pg_dump` to `~/backups/` on the VM, then `aws s3 cp` to an S3 bucket. Keep 7 local + 30 in S3 (lifecycle rule). Systemd timer preferred over cron for logging consistency with the other services.
2. **Postgres binding** — bind to the Tailscale interface on `jones.quagga-chicken.ts.net`. Clients connect via the MagicDNS name (stable across re-registration; IPs can change). Update `postgresql.conf` `listen_addresses` and `pg_hba.conf` to allow the tailnet CIDR (`100.64.0.0/10`) with `scram-sha-256`.
3. **Supabase** — pause the project after Phase 5 smoke test. Keep paused for 2 weeks as rollback safety net, then delete.

## Phase 6 — Backups to S3 (~1h)

1. Install `awscli` on the VM; configure an IAM user with `s3:PutObject` only on `s3://<bucket>/kb-backups/*`.
2. Create `/usr/local/bin/kb-backup.sh`:
   ```bash
   #!/bin/bash
   set -euo pipefail
   TS=$(date -u +%Y%m%dT%H%M%SZ)
   OUT=~/backups/kb-$TS.sql.gz
   pg_dump "postgresql://kb@localhost/kb" | gzip > "$OUT"
   aws s3 cp "$OUT" "s3://$KB_BACKUP_BUCKET/kb-backups/"
   find ~/backups -name 'kb-*.sql.gz' -mtime +7 -delete
   ```
3. Create `kb-backup.service` + `kb-backup.timer` (daily at 03:00 UTC) alongside the existing service units.
4. Add S3 lifecycle rule: transition to Glacier after 30 days, delete after 180.
5. Test restore path once: pull newest dump, `gunzip | psql` into a scratch DB, verify row counts.

**Exit criteria:** One successful timer-driven backup uploaded to S3 and restore rehearsed.
