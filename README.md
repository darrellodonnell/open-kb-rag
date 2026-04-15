# open-kb-rag

Personal knowledge base with RAG — ingest via Slack, query via MCP.

Drop URLs, PDFs, or text into Slack. The bot fetches, chunks, embeds, auto-tags, and stores everything to Supabase + markdown on disk. Query via MCP from any AI client on the tailnet.

---

## MCP Server

Running on jones at:

```
https://jones.quagga-chicken.ts.net/openkb/mcp
```

### Connect from any MCP client (Claude Desktop, Claude Code, Cursor, etc.)

```json
{
  "mcpServers": {
    "kb": {
      "type": "streamable",
      "url": "https://jones.quagga-chicken.ts.net/openkb/mcp"
    }
  }
}
```

Requires Tailscale — must be connected to `quagga-chicken.ts.net`.

### Available Tools

| Tool | Description |
|------|-------------|
| `query` | Semantic search over the knowledge base |
| `ingest_url` | Fetch and ingest a URL |
| `ingest_document` | Ingest raw text directly |
| `list_sources` | List ingested sources with optional filters |
| `delete_source` | Delete a source and all its chunks |

---

## Ingest

Primary ingest path: Slack bot running on `minimini.quagga-chicken.ts.net`.
Drop a URL (with optional commentary) into the configured Slack channel — the bot ingests and confirms.

---

## Stack

- **Python** — FastMCP server, Slack Bolt bot
- **Supabase** — pgvector for chunk storage and semantic search
- **Ollama** — `nomic-embed-text` for embeddings, `qwen2.5` for LLM tagging/summarization
- **Tailscale** — private tailnet access only

---

## Known limitations

### URL ingest fails on sites that block scrapers

Some publishers return HTTP 403 to automated fetchers (`trafilatura`'s default user agent). This is most common on:

- Medium / Substack / TowardsAI and similar (Cloudflare or Medium anti-scrape)
- Some paywalled or registration-walled outlets
- News sites using Akamai/Datadome/PerimeterX bot protection

**Symptom** — Slack logs show:

```text
trafilatura.downloads ERROR not a 200 response: 403 for URL <url>
kb.slack.handlers ERROR Failed to ingest URL <url>: Failed to download
```

**Workarounds today:**

1. Open the article in a browser → save as PDF → drop the PDF into Slack (the PDF path works fine).
2. Copy-paste the article body and ingest via `ingest_document` (MCP tool) or paste text into Slack.
3. Use an archive mirror — e.g. `https://archive.ph/newest/<original-url>` — and ingest that.

A longer-term fix is planned: see [plans/ingest-403-workaround.md](plans/ingest-403-workaround.md).

---

## Setup

See [SETUP.md](./SETUP.md) for full instructions.
