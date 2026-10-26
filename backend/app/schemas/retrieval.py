from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RetrievalMode(StrEnum):
    METRIC_DIRECT = "metric_direct"
    HOOK_FOCUSED = "hook_focused"
    BALANCED_COMPARE = "balanced_compare"
    TRANSCRIPT_DEEP = "transcript_deep"
    STRATEGY_RECOMMENDATION = "strategy_recommendation"


class RetrievalRunRecord(BaseModel):
    id: str
    project_id: str
    query: str
    retrieval_mode: RetrievalMode
    status: str
    requested_top_k: int
    candidate_count: int
    result_count: int
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    result_chunk_ids: list[str] = Field(default_factory=list)
    duration_ms: int | None = None
    error_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class RetrievalRunListResponse(BaseModel):
    project_id: str
    total_runs: int
    runs: list[RetrievalRunRecord] = Field(default_factory=list)
