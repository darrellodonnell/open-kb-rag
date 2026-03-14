# open-kb-rag: Personal Knowledge Base with RAG

## Context

Build a personal knowledge base that captures **both your insights and the content you're referencing**. Your commentary is weighted higher for tagging, but URL content (articles, PDFs) is also fully processed. YouTube transcripts get summarized by LLM rather than chunked raw (too noisy). Ingestion via Slack, storage in Supabase pgvector, semantic search via MCP server for Claude Code, Claude, and OpenClaw. Single-user, runs on a local Tailscale network.

**Content model per ingestion:**

- **Your commentary** — always chunked, embedded, tagged. Drives tag priority.
- **Articles/PDFs** — fetched, chunked, embedded. Also informs tags but weighted lower than your commentary.
- **YouTube** — transcript fetched, summarized via LLM, summary chunked/embedded. Full transcript stored on disk for reference only.

## Stack

- **Python** with `pyproject.toml`
- **Supabase Cloud** with pgvector
- **Embeddings** — configurable provider: Ollama `nomic-embed-text` (default, free, on Tailnet) or frontier models via Anthropic API / OpenRouter
- **Generation LLM** (tagging, summarization) — configurable provider: Ollama (local, free), Anthropic API, or OpenRouter. Recommended: DeepSeek V3.2 via OpenRouter (~$0.26/$0.38 per 1M tokens — pennies/month for a personal KB)
- **Slack Bot** (Socket Mode) — v1 ingestion interface
- **MCP Server** — for Claude/OpenClaw integration

## Project Structure

```text
open-kb-rag/
├── pyproject.toml
├── .env.example
├── .gitignore
├── sql/
│   └── init.sql                # Supabase schema + pgvector + search_chunks RPC
├── src/kb/
│   ├── __init__.py
│   ├── config.py               # pydantic-settings, all env vars
│   ├── db.py                   # Supabase client
│   ├── models.py               # Pydantic models: Source, Chunk, IngestResult, QueryResult
│   ├── preflight.py            # Startup checks: DB connection, storage path
│   ├── ingest/
│   │   ├── pipeline.py         # Orchestrator: validate→fetch→sanitize→chunk→embed→tag→store
│   │   ├── fetchers.py         # Per-type: article (trafilatura), youtube (transcript), tweet, pdf
│   │   ├── sanitize.py         # Regex + optional LLM scan for prompt injection
│   │   ├── chunker.py          # Hybrid paragraph-based (~512 token target)
│   │   ├── embeddings.py       # Ollama nomic-embed-text wrapper
│   │   ├── tagger.py           # LLM-based auto-tagging via Ollama
│   │   └── storage.py          # Write markdown to disk + insert to Supabase
│   ├── query/
│   │   └── engine.py           # Embed question → search_chunks RPC → ranked results
│   ├── manage/
│   │   └── ops.py              # list_sources, delete_source, bulk_ingest
│   ├── crosspost/
│   │   └── summarize.py        # Isolated summary generation + Slack post
│   ├── slack/
│   │   ├── bot.py              # Socket Mode app
│   │   └── handlers.py         # Parse URL/PDF, call pipeline, reply confirmation
│   └── mcp/
│       └── server.py           # MCP tools: ingest_url, ingest_document, query, list_sources, delete_source
└── tests/
```

## Database Schema

Three tables + one join table in Supabase:

- **`sources`** — one row per ingested URL/document: `id` (UUID), `url`, `title`, `source_type`, `notes` (user commentary from Slack message), `chunk_count`, `markdown_path`, `ingested_at`, `metadata` (JSONB)
- **`chunks`** — one row per text chunk: `id` (UUID), `source_id` (FK → sources, CASCADE), `chunk_index`, `content`, `content_type` ('commentary' | 'reference'), `token_count`, `embedding` (vector(768)), `created_at`
- **`tags`** — one row per unique tag: `id` (UUID), `name` (TEXT, UNIQUE), `created_at`
- **`source_tags`** — join table: `source_id` (FK → sources, CASCADE), `tag_id` (FK → tags, CASCADE), primary key on both

Indexes: HNSW on embeddings (cosine), unique on `tags.name`, btree on source_type and ingested_at.

Tag management: rename/merge by updating `tags.name`. Tag cloud via `SELECT t.name, count(*) FROM tags t JOIN source_tags st ON t.id = st.tag_id GROUP BY t.name`. `search_chunks` RPC joins through source_tags for tag filtering.

Full SQL in `sql/init.sql`.

## Key Dependencies

`supabase`, `httpx`, `pydantic`, `pydantic-settings`, `ollama`, `anthropic`, `trafilatura`, `youtube-transcript-api`, `pymupdf`, `tiktoken`, `slack-bolt`, `mcp`, `bleach`, `ruff`, `pytest`

## Implementation Phases

### Phase 0: Setup Guide

Write `SETUP.md` with detailed, step-by-step instructions for:

- **Supabase**: account creation, project creation, enabling pgvector (Extensions page), finding Project URL + API key (Settings → API), running `sql/init.sql` in SQL Editor
- **Ollama**: install, pull `nomic-embed-text` + LLM model, verify with curl, Tailscale IP notes
- **Slack App**: create app at api.slack.com, enable Socket Mode, add bot scopes (chat:write, channels:history, channels:read, files:read), install to workspace, get xoxb-/xapp- tokens, invite bot to channel
- **Project**: clone, venv, install deps, configure .env, create storage directory
- **Verification**: check each service, run preflight
- **Deployment**: Ubuntu VM instructions (apt deps, systemd service files for Slack bot + MCP server)

**Environment notes**: Development on macOS, deployment target is Ubuntu VM on Tailnet (likely co-located with Ollama). SETUP.md must cover both.

### Phase 1: Foundation

1. `pyproject.toml`, `.env.example`, `.gitignore`
2. `config.py` — pydantic-settings with all env vars (Supabase, Ollama, Slack, storage path)
3. `db.py` — Supabase client init
4. `models.py` — Pydantic models
5. `preflight.py` — validate DB connection, storage path exists
6. `sql/init.sql` — run manually in Supabase SQL editor

### Phase 2: Ingestion Core

1. `embeddings.py` — Ollama embed wrapper (`embed(text)`, `embed_batch(texts)`)
2. `chunker.py` — Split on `\n\n`, merge small paragraphs to ~512 tokens, split large on sentence boundaries
3. `sanitize.py` — Regex patterns for injection markers + optional LLM scan
4. `tagger.py` — Ollama generate tags from both commentary and fetched content. Commentary weighted higher in prompt. Both inform the tag set.
5. `fetchers.py` — URL type detection + per-type fetch (trafilatura for articles, youtube-transcript-api, pymupdf for PDFs, FxTwitter API for tweets). YouTube: fetch transcript then LLM-summarize (don't chunk raw transcript).
6. `storage.py` — Write markdown to `{KB_STORAGE_PATH}/{YYYY}/{MM}/{title}.md`, insert source + chunks to Supabase
7. `pipeline.py` — Orchestrate: chunk/embed commentary (content_type='commentary'), fetch URL content, chunk/embed that (content_type='reference'; for YouTube: summarize transcript first), tag from both streams (commentary weighted higher), store all

### Phase 3: Query Engine

1. `query/engine.py` — Embed question, call `search_chunks` RPC, return ranked results with source metadata

### Phase 4: Management

1. `manage/ops.py` — list_sources (with filters), delete_source (DB + disk), bulk_ingest

### Phase 5: Slack Bot

1. `slack/bot.py` — Slack Bolt Socket Mode app
2. `slack/handlers.py` — Parse message: extract URL(s), detect PDF uploads, capture any accompanying commentary text. Pass commentary to pipeline as user context (stored on source metadata, fed to tagger for better tag generation). Reply with title + tags + chunk count.

### Phase 6: Cross-post

1. `crosspost/summarize.py` — Generate summary via Ollama (isolated, never raw content in agent loop), strip UTM params, post to configured channel

### Phase 7: MCP Server

1. `mcp/server.py` — Tools: `ingest_url`, `ingest_document`, `query`, `list_sources`, `delete_source`

### Phase 8: Polish

1. Tests for chunker, sanitizer, pipeline
2. README update

## Key Design Decisions

- **No lock file, no unique URL constraint** — concurrent ingestions are independent; re-ingesting a URL is allowed (content may have changed, additive not destructive)
- **Configurable providers for both embedding and generation** — each independently set to `ollama`, `anthropic`, or `openrouter` via `EMBED_PROVIDER` and `LLM_PROVIDER` env vars. Default: Ollama for both (free, on Tailnet). Swap to frontier models when quality matters more than cost.
- **Markdown on disk** (`~/kb-store/{YYYY}/{MM}/`) + chunks in Supabase — full docs browsable, chunks searchable
- **trafilatura** for articles (no headless browser needed)
- **FxTwitter API** for tweets (avoids paid Twitter API)
- **Hybrid chunking** — paragraph-based with merge/split for ~512 token target
- **supabase-py** (sync) — adequate for single-user, avoids async complexity
- **Sanitization regex-first**, LLM scan opt-in via `SANITIZE_LLM_SCAN` env var
- **Cross-post summary isolated** — untrusted content never enters agent conversation loop
- **Normalized tags** — separate `tags` table + join table for clean tag management, rename/merge support, evolving tag cloud

## Config (.env)

```ini
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
OLLAMA_HOST=http://localhost:11434

# Embedding — pick one provider
EMBED_PROVIDER=ollama                         # ollama | anthropic | openrouter
OLLAMA_EMBED_MODEL=nomic-embed-text           # used when EMBED_PROVIDER=ollama
ANTHROPIC_EMBED_MODEL=...                     # used when EMBED_PROVIDER=anthropic
OPENROUTER_EMBED_MODEL=...                    # used when EMBED_PROVIDER=openrouter

# Generation LLM — pick one provider
LLM_PROVIDER=ollama                           # ollama | anthropic | openrouter
OLLAMA_LLM_MODEL=llama3.2                    # used when LLM_PROVIDER=ollama
ANTHROPIC_MODEL=claude-sonnet-4-6             # used when LLM_PROVIDER=anthropic
OPENROUTER_MODEL=deepseek/deepseek-v3.2       # used when LLM_PROVIDER=openrouter (recommended)

# API keys (needed if using anthropic or openrouter for either embedding or generation)
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
KB_STORAGE_PATH=~/kb-store
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_CHANNEL_ID=C0123456789
SLACK_CROSSPOST_CHANNEL_ID=C9876543210
SANITIZE_LLM_SCAN=false
```

## Verification

1. **Phase 1**: Run `preflight.py` — confirms DB connection and storage path
2. **Phase 2**: Ingest a test URL via `pipeline.py` directly — verify chunks + embedding in Supabase, markdown on disk
3. **Phase 3**: Query with a test question — verify relevant chunks returned
4. **Phase 5**: Post a URL in Slack channel — verify bot responds with confirmation
5. **Phase 7**: Configure MCP server in Claude Code, call `query` tool — verify results
6. **End-to-end**: Drop a URL in Slack → bot ingests → query via MCP in Claude Code → get relevant chunks back
