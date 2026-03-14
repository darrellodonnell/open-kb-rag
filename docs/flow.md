# open-kb-rag: Data Flow

## Ingestion Flow

```
                        +-----------------+
                        |   Input Sources  |
                        +-----------------+
                               |
              +----------------+----------------+
              |                |                |
        Slack Message     MCP Tool Call    Direct API
        (bot.py)          (server.py)     (pipeline.py)
              |                |                |
              v                v                v
     +------------------+  Extract URLs, PDFs, commentary
     | handlers.py      |  from Slack message format
     +--------+---------+
              |
              +----> commentary text (user's own words)
              +----> URL(s) found in message
              +----> PDF file uploads
              |
              v
    +--------------------+
    |   pipeline.py      |   Orchestrator
    +---------+----------+
              |
    +---------+-----------------------------------------+
    |                                                   |
    v                                                   v
  COMMENTARY PATH                              REFERENCE PATH
  (content_type='commentary')                  (content_type='reference')
    |                                                   |
    |                                          +--------+--------+
    |                                          |  fetch_url()    |
    |                                          |  fetchers.py    |
    |                                          +--------+--------+
    |                                                   |
    |                                     +-------------+-------------+
    |                                     |             |             |
    |                                     v             v             v
    |                                 ARTICLE       YOUTUBE        TWEET
    |                                trafilatura   transcript    FxTwitter
    |                                               API         VxTwitter
    |                                     |             |        oEmbed
    |                                     |             |             |
    |                                     v             v             v
    |                                     +------+------+------+------+
    |                                            |             |
    |                                            v             v
    |                                       PDF from URL    PDF Upload
    |                                        httpx +        pymupdf
    |                                        pymupdf
    |                                            |
    |                                            v
    |                                    +---------------+
    |                                    | sanitize.py   |
    |                                    | 1. Strip HTML |
    |                                    | 2. Regex scan |
    |                                    | 3. LLM scan   |
    |                                    |    (optional)  |
    |                                    +-------+-------+
    |                                            |
    |                                    YouTube only:
    |                                    +---------------+
    |                                    | LLM summarize |
    |                                    | (llm.py)      |
    |                                    +-------+-------+
    |                                            |
    v                                            v
  +-------------------------------------------------+
  |              chunker.py                         |
  |  Split on paragraphs, merge small, split large  |
  |  Target: ~512 tokens per chunk                  |
  +-----------------------+-------------------------+
                          |
                          v
  +-------------------------------------------------+
  |             embeddings.py                       |
  |  embed_batch() via configured provider          |
  |  Ollama | Anthropic (Voyage) | OpenRouter       |
  |  Output: vector(768) per chunk                  |
  +-----------------------+-------------------------+
                          |
                          v
  +-------------------------------------------------+
  |              tagger.py                          |
  |  LLM generates up to 8 tags                    |
  |  Commentary = PRIMARY weight                   |
  |  Reference  = SECONDARY weight                 |
  |  Output: ["tag-one", "tag-two", ...]           |
  +-----------------------+-------------------------+
                          |
                          v
  +-------------------------------------------------+
  |              storage.py                         |
  |                                                 |
  |  Disk:     ~/kb-store/{YYYY}/{MM}/title.md      |
  |                                                 |
  |  Supabase: sources    (1 row per ingestion)     |
  |            chunks     (N rows with embeddings)  |
  |            tags       (upsert unique tags)      |
  |            source_tags (join table)              |
  +-----------------------+-------------------------+
                          |
                          v
                   IngestResult
                 (source_id, title,
                  source_type, tags,
                  chunk_count)
                          |
                          v
               Slack confirmation reply
         "Ingested: *Title* | Chunks: N | Tags: ..."


## Query Flow

  +---------------------+
  |  User Question      |
  |  (natural language)  |
  +---------+-----------+
            |
            v
  +---------------------+
  | embed(question)     |
  | embeddings.py       |
  | -> vector(768)      |
  +---------+-----------+
            |
            v
  +---------------------+
  | search_chunks RPC   |
  | (Supabase/pgvector) |
  |                     |
  | Cosine similarity   |
  | + optional filters: |
  |   - tags            |
  |   - source_type     |
  |   - threshold       |
  +---------+-----------+
            |
            v
  +---------------------+
  | Ranked Results      |
  | List[QueryResult]   |
  |                     |
  | - chunk content     |
  | - similarity score  |
  | - source metadata   |
  | - tags              |
  +---------+-----------+
            |
            v
    MCP / Claude Code /
    Claude / OpenClaw


## Content Type Handling Summary

| Source     | Fetch Method        | Processing              | Content Type |
|------------|---------------------|-------------------------|-------------|
| Article    | trafilatura         | chunk + embed           | reference   |
| YouTube    | transcript API      | LLM summarize, then chunk + embed | reference |
| Tweet      | FxTwitter/oEmbed    | chunk + embed           | reference   |
| PDF (URL)  | httpx + pymupdf     | chunk + embed           | reference   |
| PDF (upload)| Slack download + pymupdf | chunk + embed     | reference   |
| Commentary | from Slack message  | chunk + embed           | commentary  |
| Document   | direct text input   | chunk + embed           | reference   |
