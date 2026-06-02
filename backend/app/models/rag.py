from typing import Literal

from pydantic import BaseModel, Field


RagPlatform = Literal["youtube", "instagram"]
RagSourceType = Literal["metadata", "description", "hook", "transcript"]
IndexProjectStatus = Literal["indexed", "failed"]


class EmbeddingHealthResponse(BaseModel):
    status: str
    model_name: str
    vector_size: int | None = None
    message: str | None = None


class VectorStoreHealthResponse(BaseModel):
    status: str
    collection: str
    qdrant_configured: bool
    collections: list[str] = Field(default_factory=list)
    message: str | None = None


class RagChunk(BaseModel):
    chunk_id: str
    project_id: str
    platform: RagPlatform
    source_type: RagSourceType
    chunk_index: int
    start_time: float | None = None
    end_time: float | None = None
    title: str | None = None
    creator: str | None = None
    text: str
    content_hash: str
    citation_label: str
    qdrant_point_id: str | None = None


class ChunkBuildResponse(BaseModel):
    project_id: str
    total_chunks: int
    youtube_chunks: int
    instagram_chunks: int
    chunks: list[RagChunk] = Field(default_factory=list)


class IndexProjectResponse(BaseModel):
    project_id: str
    status: IndexProjectStatus
    embedding_model: str
    qdrant_collection: str
    total_chunks: int
    youtube_chunks: int
    instagram_chunks: int
    message: str | None = None


class RagChunkListResponse(BaseModel):
    project_id: str
    total_chunks: int
    chunks: list[RagChunk] = Field(default_factory=list)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 6
    platform: RagPlatform | None = None
    source_type: RagSourceType | None = None


class RetrievedChunk(BaseModel):
    platform: str
    source_type: str
    score: float
    chunk_index: int | None = None
    start_time: float | None = None
    end_time: float | None = None
    title: str | None = None
    creator: str | None = None
    citation_label: str
    text: str


class RetrieveResponse(BaseModel):
    project_id: str
    query: str
    applied_platform: RagPlatform | None = None
    applied_source_type: RagSourceType | None = None
    total_results: int
    results: list[RetrievedChunk] = Field(default_factory=list)
