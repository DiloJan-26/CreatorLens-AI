from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.llm_observability import LlmRun
from app.db.repositories._utils import utc_now
from app.llm.token_usage import TokenUsage


class LlmRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def start(
        self,
        *,
        project_id: str,
        llm_provider: str,
        llm_model: str,
        prompt_name: str | None,
        prompt_version: str | None,
        session_id: str | None = None,
        retrieval_run_id: str | None = None,
        retrieved_chunk_count: int | None = None,
        source_balance: dict[str, Any] | None = None,
    ) -> LlmRun:
        run = LlmRun(
            id=str(uuid4()),
            project_id=project_id,
            session_id=_optional_text(session_id, 128),
            retrieval_run_id=_optional_text(retrieval_run_id, 36),
            langsmith_trace_id=None,
            status="RUNNING",
            llm_provider=_required_text(llm_provider, 32),
            llm_model=_required_text(llm_model, 128),
            prompt_name=_optional_text(prompt_name, 128),
            prompt_version=_optional_text(prompt_version, 32),
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            retrieval_latency_ms=None,
            llm_latency_ms=None,
            retrieved_chunk_count=_optional_count(retrieved_chunk_count),
            source_balance=dict(source_balance or {}),
            cache_hit=None,
            cache_miss=None,
            transcript_provider=None,
            transcript_fallback_used=None,
            embedding_reused=None,
            error_code=None,
            created_at=utc_now(),
            completed_at=None,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def complete(
        self,
        run_id: str,
        *,
        usage: TokenUsage | None = None,
        retrieval_latency_ms: int | None = None,
        llm_latency_ms: int | None = None,
        retrieved_chunk_count: int | None = None,
        source_balance: dict[str, Any] | None = None,
        cache_hit: bool | None = None,
        cache_miss: bool | None = None,
        transcript_provider: str | None = None,
        transcript_fallback_used: bool | None = None,
        embedding_reused: bool | None = None,
        langsmith_trace_id: str | None = None,
    ) -> bool:
        run = self.session.get(LlmRun, run_id)
        if run is None:
            return False

        run.status = "COMPLETED"
        self._apply_observability(
            run,
            usage=usage,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            retrieved_chunk_count=retrieved_chunk_count,
            source_balance=source_balance,
            cache_hit=cache_hit,
            cache_miss=cache_miss,
            transcript_provider=transcript_provider,
            transcript_fallback_used=transcript_fallback_used,
            embedding_reused=embedding_reused,
            langsmith_trace_id=langsmith_trace_id,
        )
        run.error_code = None
        run.completed_at = utc_now()
        self.session.flush()
        return True

    def fail(
        self,
        run_id: str,
        *,
        error_code: str,
        usage: TokenUsage | None = None,
        retrieval_latency_ms: int | None = None,
        llm_latency_ms: int | None = None,
        langsmith_trace_id: str | None = None,
    ) -> bool:
        run = self.session.get(LlmRun, run_id)
        if run is None:
            return False

        run.status = "FAILED"
        self._apply_observability(
            run,
            usage=usage,
            retrieval_latency_ms=retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        run.error_code = _required_text(error_code, 64)
        run.completed_at = utc_now()
        self.session.flush()
        return True

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self.session.get(LlmRun, run_id)
        return self.to_record(run) if run is not None else None

    def list_for_project(
        self,
        project_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        runs = self.session.scalars(
            select(LlmRun)
            .where(LlmRun.project_id == project_id)
            .order_by(LlmRun.created_at.desc())
            .limit(max(1, min(limit, 200)))
        ).all()
        return [self.to_record(run) for run in runs]

    @staticmethod
    def _apply_observability(
        run: LlmRun,
        *,
        usage: TokenUsage | None = None,
        retrieval_latency_ms: int | None = None,
        llm_latency_ms: int | None = None,
        retrieved_chunk_count: int | None = None,
        source_balance: dict[str, Any] | None = None,
        cache_hit: bool | None = None,
        cache_miss: bool | None = None,
        transcript_provider: str | None = None,
        transcript_fallback_used: bool | None = None,
        embedding_reused: bool | None = None,
        langsmith_trace_id: str | None = None,
    ) -> None:
        if usage is not None:
            run.input_tokens = _optional_count(usage.input_tokens)
            run.output_tokens = _optional_count(usage.output_tokens)
            run.total_tokens = _optional_count(usage.total_tokens)
        if retrieval_latency_ms is not None:
            run.retrieval_latency_ms = max(retrieval_latency_ms, 0)
        if llm_latency_ms is not None:
            run.llm_latency_ms = max(llm_latency_ms, 0)
        if retrieved_chunk_count is not None:
            run.retrieved_chunk_count = max(retrieved_chunk_count, 0)
        if source_balance is not None:
            run.source_balance = dict(source_balance)
        if cache_hit is not None:
            run.cache_hit = cache_hit
        if cache_miss is not None:
            run.cache_miss = cache_miss
        if transcript_provider is not None:
            run.transcript_provider = _optional_text(transcript_provider, 64)
        if transcript_fallback_used is not None:
            run.transcript_fallback_used = transcript_fallback_used
        if embedding_reused is not None:
            run.embedding_reused = embedding_reused
        if langsmith_trace_id is not None:
            run.langsmith_trace_id = _optional_text(langsmith_trace_id, 128)

    @staticmethod
    def to_record(run: LlmRun) -> dict[str, Any]:
        return {
            column.name: getattr(run, column.name)
            for column in run.__table__.columns
        }


def _required_text(value: str, limit: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Required observability text cannot be empty.")
    return normalized[:limit]


def _optional_text(value: str | None, limit: int) -> str | None:
    normalized = (value or "").strip()
    return normalized[:limit] if normalized else None


def _optional_count(value: int | None) -> int | None:
    return max(value, 0) if value is not None else None
