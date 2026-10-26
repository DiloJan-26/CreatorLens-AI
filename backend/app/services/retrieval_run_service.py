import logging
from typing import Any

from app.db.repositories.retrieval_repository import RetrievalRepository
from app.db.session import database_session, is_database_configured


logger = logging.getLogger(__name__)


def start_retrieval_run(
    *,
    project_id: str,
    query: str,
    retrieval_mode: str,
    requested_top_k: int,
    applied_filters: dict[str, Any],
) -> str | None:
    if not is_database_configured():
        return None
    try:
        with database_session() as session:
            return RetrievalRepository(session).start(
                project_id=project_id,
                query=query,
                retrieval_mode=retrieval_mode,
                requested_top_k=requested_top_k,
                applied_filters=applied_filters,
            ).id
    except Exception:
        logger.exception(
            "Could not start retrieval run project_id=%s mode=%s",
            project_id,
            retrieval_mode,
        )
        return None


def complete_retrieval_run(
    run_id: str | None,
    *,
    candidate_count: int,
    result_chunk_ids: list[str],
    duration_ms: int,
) -> None:
    if run_id is None or not is_database_configured():
        return
    try:
        with database_session() as session:
            RetrievalRepository(session).complete(
                run_id,
                candidate_count=candidate_count,
                result_chunk_ids=result_chunk_ids,
                duration_ms=duration_ms,
            )
    except Exception:
        logger.exception("Could not complete retrieval run run_id=%s", run_id)


def fail_retrieval_run(
    run_id: str | None,
    *,
    error_code: str,
    duration_ms: int,
) -> None:
    if run_id is None or not is_database_configured():
        return
    try:
        with database_session() as session:
            RetrievalRepository(session).fail(
                run_id,
                error_code=error_code,
                duration_ms=duration_ms,
            )
    except Exception:
        logger.exception("Could not fail retrieval run run_id=%s", run_id)


def list_project_retrieval_runs(
    project_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not is_database_configured():
        return []
    with database_session() as session:
        return RetrievalRepository(session).list_for_project(project_id, limit)
