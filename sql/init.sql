-- open-kb-rag: Supabase schema
-- Run this in the Supabase SQL Editor after enabling the pgvector extension.

-- Ensure pgvector is available
create extension if not exists vector with schema extensions;

-- ============================================================
-- sources: one row per ingested URL or document
-- ============================================================
create table if not exists sources (
    id          uuid primary key default gen_random_uuid(),
    url         text,
    title       text not null,
    source_type text not null,                       -- 'article' | 'youtube' | 'tweet' | 'pdf' | 'document'
    notes       text,                                -- user commentary from Slack message
    chunk_count integer not null default 0,
    markdown_path text,                              -- relative path in kb-store
    ingested_at timestamptz not null default now(),
    metadata    jsonb not null default '{}'::jsonb
);

create index if not exists idx_sources_source_type on sources (source_type);
create index if not exists idx_sources_ingested_at on sources (ingested_at desc);

-- ============================================================
-- chunks: one row per text chunk with embedding
-- ============================================================
create table if not exists chunks (
    id           uuid primary key default gen_random_uuid(),
    source_id    uuid not null references sources(id) on delete cascade,
    chunk_index  integer not null,
    content      text not null,
    content_type text not null default 'reference',  -- 'commentary' | 'reference'
    token_count  integer not null,
    embedding    vector(768),                        -- nomic-embed-text dimension
    created_at   timestamptz not null default now()
);

create index if not exists idx_chunks_source_id on chunks (source_id);

-- HNSW index for fast cosine similarity search
create index if not exists idx_chunks_embedding on chunks
    using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- ============================================================
-- tags: normalized tag table
-- ============================================================
create table if not exists tags (
    id         uuid primary key default gen_random_uuid(),
    name       text not null unique,
    created_at timestamptz not null default now()
);

-- ============================================================
-- source_tags: join table
-- ============================================================
create table if not exists source_tags (
    source_id uuid not null references sources(id) on delete cascade,
    tag_id    uuid not null references tags(id) on delete cascade,
    primary key (source_id, tag_id)
);

-- ============================================================
-- search_chunks: RPC for semantic search with optional tag filter
-- ============================================================
create or replace function search_chunks(
    query_embedding vector(768),
    match_count     integer default 10,
    similarity_threshold float default 0.0,
    filter_tags     text[] default null,
    filter_source_type text default null
)
returns table (
    chunk_id       uuid,
    source_id      uuid,
    chunk_index    integer,
    content        text,
    content_type   text,
    token_count    integer,
    similarity     float,
    source_url     text,
    source_title   text,
    source_type    text,
    source_notes   text,
    ingested_at    timestamptz,
    tags           text[]
)
language plpgsql
as $$
begin
    return query
    select
        c.id            as chunk_id,
        c.source_id,
        c.chunk_index,
        c.content,
        c.content_type,
        c.token_count,
        1 - (c.embedding <=> query_embedding) as similarity,
        s.url           as source_url,
        s.title         as source_title,
        s.source_type,
        s.notes         as source_notes,
        s.ingested_at,
        coalesce(
            array_agg(distinct t.name) filter (where t.name is not null),
            '{}'::text[]
        ) as tags
    from chunks c
    join sources s on s.id = c.source_id
    left join source_tags st on st.source_id = s.id
    left join tags t on t.id = st.tag_id
    where
        (1 - (c.embedding <=> query_embedding)) >= similarity_threshold
        and (filter_source_type is null or s.source_type = filter_source_type)
        and (
            filter_tags is null
            or s.id in (
                select st2.source_id
                from source_tags st2
                join tags t2 on t2.id = st2.tag_id
                where t2.name = any(filter_tags)
            )
        )
    group by c.id, c.source_id, c.chunk_index, c.content, c.content_type,
             c.token_count, c.embedding, s.url, s.title, s.source_type,
             s.notes, s.ingested_at
    order by similarity desc
    limit match_count;
end;
$$;
