from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class CostTotals(BaseModel):
    event_count: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    total_tokens: int | None = 0
    estimated_cost_usd: Decimal | None = None

    total_operations: int = 0
    model_invocations: int = 0
    inference_events: int = 0
    priced_inference_events: int = 0
    unpriced_inference_events: int = 0
    deterministic_operations: int = 0
    known_zero_events: int = 0
    legacy_invocation_unknown: int = 0
    priced_subtotal_usd: Decimal | None = None
    actual_billed_cost_usd: Decimal | None = None
    pricing_coverage: float | None = None
    verified_pricing_coverage: float | None = None
    legacy_estimate_events: int = 0
    cost_status: str = 'not_measured'


class LlmRunSummary(BaseModel):
    id: str
    project_id: str | None
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
    operation_type: str | None = None
    execution_mode: str | None = None
    provider_invocation_count: int | None = None
    end_to_end_latency_ms: int | None = None
    context_latency_ms: int | None = None
    deterministic_latency_ms: int | None = None
    telemetry: dict | None = None
    cost_events: list[dict] = Field(default_factory=list)


class CostMetricsResponse(BaseModel):
    project_id: str | None = None
    totals: CostTotals
    analytics: dict = Field(default_factory=dict)
    runs: list[LlmRunSummary] = Field(default_factory=list)
