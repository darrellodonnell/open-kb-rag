Build a knowledge base with RAG (Retrieval-Augmented Generation):

1. Ingestion pipeline:
   - Accept URLs (articles, tweets, YouTube, PDFs)
   - Validate URL scheme (http/https only, reject file://, ftp://, etc.)
   - Fetch content using appropriate methods per source type
   - Sanitize untrusted content before processing:
     * Deterministic pass: regex for injection patterns
     * Optional model-based pass: semantic scanner for sophisticated attacks
   - Chunk text and generate embeddings (local model to avoid API costs)
   - Store in Supabase with source URL, title, tags, and chunk metadata
   - Use a lock file to prevent concurrent ingestions

2. Cross-post script:
   - After ingesting, optionally post a summary to another channel (e.g., Slack)
   - Keep untrusted page content out of the agent's conversation loop
   - Clean summaries: strip metadata, tracking params, UTM tags

3. Query engine:
   - Semantic search over embeddings
   - Filter by tag, source type, date range
   - Configurable result limit and similarity threshold

4. Preflight checks:
   - Validate required paths and databases before every KB operation
   - Alert on missing paths or corrupted state
   - Check for stale lock files (kill if owning PID is dead)

5. Management:
   - List sources with filters
   - Delete by source ID
   - Bulk ingest from a file of URLs

6. Usages:
   - to be used in Claude, Claude Code, and OpenClaw as both a sink and source (query)
