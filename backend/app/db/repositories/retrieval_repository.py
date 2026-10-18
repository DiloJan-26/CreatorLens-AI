from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.retrieval_run import RetrievalRun
from app.db.repositories._utils import utc_now


class RetrievalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def start(
        self,
        *,
        project_id: str,
        query: str,
        retrieval_mode: str,
        requested_top_k: int,
        applied_filters: dict[str, Any] | None = None,
    ) -> RetrievalRun:
        run = RetrievalRun(
            id=str(uuid4()),
            project_id=project_id,
            query=query,
            retrieval_mode=retrieval_mode,
            status="RUNNING",
            requested_top_k=requested_top_k,
            candidate_count=0,
            result_count=0,
            applied_filters=dict(applied_filters or {}),
            result_chunk_ids=[],
            duration_ms=None,
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
        candidate_count: int,
        result_chunk_ids: list[str],
        duration_ms: int,
    ) -> bool:
        run = self.session.get(RetrievalRun, run_id)
        if run is None:
            return False

        run.status = "COMPLETED"
        run.candidate_count = max(candidate_count, 0)
        run.result_chunk_ids = list(result_chunk_ids)
        run.result_count = len(result_chunk_ids)
        run.duration_ms = max(duration_ms, 0)
        run.error_code = None
        run.completed_at = utc_now()
        self.session.flush()
        return True

    def fail(
        self,
        run_id: str,
        *,
        error_code: str,
        duration_ms: int,
    ) -> bool:
        run = self.session.get(RetrievalRun, run_id)
        if run is None:
            return False

        run.status = "FAILED"
        run.duration_ms = max(duration_ms, 0)
        run.error_code = error_code[:64]
        run.completed_at = utc_now()
        self.session.flush()
        return True

    def get(self, run_id: str) -> dict[str, Any] | None:
        run = self.session.get(RetrievalRun, run_id)
        return self.to_record(run) if run is not None else None

    def list_for_project(
        self, project_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 200))
        runs = self.session.scalars(
            select(RetrievalRun)
            .where(RetrievalRun.project_id == project_id)
            .order_by(RetrievalRun.created_at.desc())
            .limit(safe_limit)
        ).all()
        return [self.to_record(run) for run in runs]

    @staticmethod
    def to_record(run: RetrievalRun) -> dict[str, Any]:
        return {
            "id": run.id,
            "project_id": run.project_id,
            "query": run.query,
            "retrieval_mode": run.retrieval_mode,
            "status": run.status,
            "requested_top_k": run.requested_top_k,
            "candidate_count": run.candidate_count,
            "result_count": run.result_count,
            "applied_filters": dict(run.applied_filters or {}),
            "result_chunk_ids": list(run.result_chunk_ids or []),
            "duration_ms": run.duration_ms,
            "error_code": run.error_code,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }
