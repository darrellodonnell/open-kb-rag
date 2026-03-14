"""Pydantic models for sources, chunks, and query results."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    article = "article"
    youtube = "youtube"
    tweet = "tweet"
    pdf = "pdf"
    document = "document"


class ContentType(str, Enum):
    commentary = "commentary"
    reference = "reference"


class Source(BaseModel):
    id: UUID
    url: Optional[str] = None
    title: str
    source_type: SourceType
    notes: Optional[str] = None
    chunk_count: int = 0
    markdown_path: Optional[str] = None
    ingested_at: datetime
    metadata: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class Chunk(BaseModel):
    id: UUID
    source_id: UUID
    chunk_index: int
    content: str
    content_type: ContentType
    token_count: int
    created_at: datetime


class IngestResult(BaseModel):
    source_id: UUID
    title: str
    source_type: SourceType
    tags: list[str]
    chunk_count: int
    markdown_path: Optional[str] = None


class QueryResult(BaseModel):
    chunk_id: UUID
    source_id: UUID
    chunk_index: int
    content: str
    content_type: ContentType
    token_count: int
    similarity: float
    source_url: Optional[str] = None
    source_title: str
    source_type: SourceType
    source_notes: Optional[str] = None
    ingested_at: datetime
    tags: list[str] = Field(default_factory=list)
