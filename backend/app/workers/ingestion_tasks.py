import logging
from uuid import uuid4

from app.schemas.ingestion import IngestionJobStatus
from app.services.project_service import (
    build_and_store_project_chunks,
    extract_project_videos,
)
from app.workers.celery_app import celery_app
from app.workers.job_runtime import (
    job_context,
    retry_or_fail_job,
    set_job_task_id,
    start_or_restart_job,
    transition_job,
)


logger = logging.getLogger(__name__)


class EmptyEvidenceError(RuntimeError):
    """Raised when extraction produces no evidence chunks to index."""


@celery_app.task(
    bind=True,
    name="creatorlens.ingest_project",
)
def ingest_project_task(self, job_id: str) -> dict[str, str]:
    project_id, current = job_context(job_id)
    if current in {
        IngestionJobStatus.EMBEDDING,
        IngestionJobStatus.INDEXING,
        IngestionJobStatus.READY,
        IngestionJobStatus.PARTIAL_READY,
        IngestionJobStatus.FAILED,
    }:
        logger.info(
            "Ignoring duplicate or superseded ingestion delivery job_id=%s "
            "project_id=%s status=%s",
            job_id,
            project_id,
            current.value,
        )
        return {"job_id": job_id, "status": current.value}

    try:
        if not start_or_restart_job(
            job_id,
            IngestionJobStatus.EXTRACTING_METADATA,
        ):
            return {"job_id": job_id, "status": current.value}

        logger.info(
            "Worker extraction started job_id=%s project_id=%s",
            job_id,
            project_id,
        )
        extract_project_videos(project_id)
        transition_job(job_id, IngestionJobStatus.EXTRACTING_TRANSCRIPT)
        transition_job(job_id, IngestionJobStatus.CHUNKING)

        chunk_result = build_and_store_project_chunks(project_id)
        if chunk_result.total_chunks == 0:
            raise EmptyEvidenceError(
                "Extraction completed without evidence that can be indexed."
            )

        from app.workers.indexing_tasks import index_project_task

        index_task_id = str(uuid4())
        set_job_task_id(job_id, index_task_id)
        index_project_task.apply_async(
            args=[job_id],
            task_id=index_task_id,
        )
        logger.info(
            "Worker extraction completed and indexing queued job_id=%s "
            "project_id=%s total_chunks=%s",
            job_id,
            project_id,
            chunk_result.total_chunks,
        )
        return {"job_id": job_id, "status": IngestionJobStatus.CHUNKING.value}
    except Exception as exc:
        retry_or_fail_job(
            self,
            job_id=job_id,
            project_id=project_id,
            exc=exc,
            error_code="INGESTION_FAILED",
            fallback_message="Background ingestion failed.",
        )
        raise AssertionError("retry_or_fail_job must raise")

