# Plan: Get past HTTP 403 on URL ingest

**Status:** Draft
**Date:** 2026-04-15
**Problem:** `trafilatura` gets HTTP 403 from a growing set of publishers (Medium, Substack, TowardsAI, Cloudflare-fronted sites). Today these URLs fail silently with a Slack error — user has to manually save-as-PDF or paste text.

---

## Goal

When trafilatura returns 403/401/429 (or other "blocked" signals), automatically retry via a fallback fetcher that can handle anti-bot defenses. The user should be unaware the fallback happened — they just drop a URL in Slack and it works.

## Non-goals

- No change to chunking, embedding, or storage. The only change is *how* we get the raw HTML/text before chunking.
- Not trying to bypass real paywalls (NYT, WSJ). Those should continue to fail — the user pastes text if they have legit access.

---

## Options, ranked by effort

### 1. Jina Reader (r.jina.ai) — free, remote, no infra

- Public API: `GET https://r.jina.ai/<any-url>` returns clean markdown extraction.
- Handles Medium/Cloudflare/most bot-protected sites (it runs its own headless browser farm).
- Free tier: rate-limited but generous for personal use; authenticated tier available.
- **Pros:** ~10 lines of code. Zero infra. Solves 80%+ of real-world 403s.
- **Cons:** Third-party dependency, URLs leak to Jina, rate limits.
- **Effort:** 1–2 hours (add `jina_fallback.py`, wire into `kb/ingest/fetcher.py`).

### 2. Playwright + Chromium headless (self-hosted)

- Run a lightweight browser via Playwright on jones, fetch the page, strip JS, pass HTML to trafilatura's `extract()`.
- **Pros:** Runs locally on jones, no third-party data leak, no rate limits, handles JS-heavy SPAs that Jina might struggle with.
- **Cons:** +1 GB disk for Chromium, needs ongoing browser updates, adds CPU/memory cost per ingest (~2–3 s + ~200 MB RAM per fetch).
- **Effort:** 4–6 hours (install, wrap, stealth plugin, test on known-hostile sites).

### 3. Claude in Chrome (Claude Agent SDK + browser tool)

- Spawn a Claude-driven browser session, let Claude navigate + extract (handles cookie walls, "continue reading" prompts, dynamic paywalls).
- **Pros:** Best-in-class at novel anti-bot defenses; can click through interstitials.
- **Cons:** Heaviest setup (Claude API cost per ingest, Docker or Chrome on jones, Agent SDK wiring), slowest (10+ seconds per ingest), overkill for most cases.
- **Effort:** 1–2 days (SDK setup, tool definition, per-site prompt tuning, cost monitoring).

### 4. Commercial scraping APIs (ScrapingBee, Bright Data, ZenRows)

- **Pros:** Highest success rate, enterprise-grade.
- **Cons:** Paid (~$30–50/mo for personal volume), third-party data leak.
- **Effort:** 2–3 hours.

---

## Recommended path (tiered fallback)

Cheapest-first retry chain so most URLs resolve via the fastest tier:

```
trafilatura (local, fast)
    ↓ 403/401/429
Jina Reader (free, remote)
    ↓ still fails
[optional later] Playwright (local, heavy)
    ↓ still fails
[optional later] Claude in Chrome (agentic)
    ↓ still fails
Surface error to Slack with workaround hint ("save as PDF, drop in channel")
```

**Phase A (this plan's first PR):** trafilatura → Jina fallback. Covers the realistic 80%.

**Phase B (if needed):** add Playwright as tier 3 when a site defeats Jina.

**Phase C (aspirational):** Claude in Chrome for truly hostile sites — only if Phase B still has gaps.

Most likely Phase A alone is sufficient indefinitely.

---

## Phase A implementation sketch

**New module:** `src/kb/ingest/fetchers/jina.py`

```python
import httpx
from kb.config import settings

def fetch_via_jina(url: str) -> tuple[str, dict]:
    """Fallback fetcher using r.jina.ai. Returns (markdown, metadata)."""
    r = httpx.get(
        f"https://r.jina.ai/{url}",
        headers={"Accept": "text/markdown", "X-Return-Format": "markdown",
                 "Authorization": f"Bearer {settings.jina_api_key}" if settings.jina_api_key else ""},
        timeout=30.0,
    )
    r.raise_for_status()
    return r.text, {"fetcher": "jina"}
```

**Modified:** `src/kb/ingest/fetcher.py` (or wherever trafilatura is called) — wrap the trafilatura call, catch the 403/401/429 HTTP errors, retry via `fetch_via_jina()`, log which tier succeeded.

**Config:** add optional `JINA_API_KEY` env var (free tier works without it; authenticated tier has higher rate limits).

**Tests:** mock httpx against known-good and known-403 URLs; verify fallback triggers on 403, not on 500.

**Observability:** log `fetcher=trafilatura|jina|failed` per ingest so we can see the fallback rate and catch regressions.

---

## Open questions

1. **Free tier vs authenticated Jina** — start free, add API key only if rate limiting bites?
2. **Extraction quality** — Jina returns markdown already, not HTML. We need to decide whether to skip trafilatura's `extract()` step when the source is Jina (it's double-processing) or run it anyway for consistency.
3. **Privacy** — any concern about ingest URLs traveling through Jina? (Personal KB so probably not.)
