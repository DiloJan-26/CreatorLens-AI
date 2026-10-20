from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class CostTotals(BaseModel):
    event_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: Decimal | None = None


class LlmRunSummary(BaseModel):
    id: str
    project_id: str
    session_id: str | None = None
    retrieval_run_id: str | None = None
    langsmith_trace_id: str | None = None
    status: str
    llm_provider: str
    llm_model: str
    prompt_name: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    retrieval_latency_ms: int | None = None
    llm_latency_ms: int | None = None
    retrieved_chunk_count: int | None = None
    source_balance: dict[str, Any] = Field(default_factory=dict)
    cache_hit: bool | None = None
    cache_miss: bool | None = None
    transcript_provider: str | None = None
    transcript_fallback_used: bool | None = None
    embedding_reused: bool | None = None
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class CostMetricsResponse(BaseModel):
    project_id: str | None = None
    totals: CostTotals
    runs: list[LlmRunSummary] = Field(default_factory=list)
