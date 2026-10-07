import logging

from app.rag.indexing_service import index_project
from app.schemas.ingestion import IngestionJobStatus
from app.services.storage_compat_service import (
    list_video_records,
    update_project_status,
)
from app.workers.celery_app import celery_app
from app.workers.job_runtime import (
    job_context,
    retry_or_fail_job,
    start_or_restart_job,
    transition_job,
)


logger = logging.getLogger(__name__)


class EvidenceIndexingError(RuntimeError):
    """Raised when the existing indexing service reports a failed result."""


def completion_status_for_content(
    content_items: list[dict],
) -> IngestionJobStatus:
    usable_items = [
        item
        for item in content_items
        if str(item.get("extraction_status")) in {"ready", "partial"}
    ]
    if not usable_items:
        return IngestionJobStatus.FAILED

    has_two_complete_items = len(usable_items) >= 2 and all(
        str(item.get("extraction_status")) == "ready"
        and bool(item.get("transcript_available"))
        for item in usable_items
    )
    return (
        IngestionJobStatus.READY
        if has_two_complete_items
        else IngestionJobStatus.PARTIAL_READY
    )


@celery_app.task(
    bind=True,
    name="creatorlens.index_project",
)
def index_project_task(self, job_id: str) -> dict[str, str]:
    project_id, current = job_context(job_id)
    if current in {
        IngestionJobStatus.READY,
        IngestionJobStatus.PARTIAL_READY,
        IngestionJobStatus.FAILED,
    }:
        logger.info(
            "Ignoring duplicate terminal indexing delivery job_id=%s "
            "project_id=%s status=%s",
            job_id,
            project_id,
            current.value,
        )
        return {"job_id": job_id, "status": current.value}

    try:
        if not start_or_restart_job(job_id, IngestionJobStatus.EMBEDDING):
            return {"job_id": job_id, "status": current.value}

        logger.info(
            "Worker embedding/indexing started job_id=%s project_id=%s",
            job_id,
            project_id,
        )
        index_result = index_project(project_id, rebuild_chunks=False)
        transition_job(job_id, IngestionJobStatus.INDEXING)
        if index_result.status != "indexed":
            raise EvidenceIndexingError(
                index_result.message or "Evidence indexing failed."
            )

        final_status = completion_status_for_content(
            list_video_records(project_id)
        )
        if final_status == IngestionJobStatus.FAILED:
            raise EvidenceIndexingError(
                "No usable extracted content remained after indexing."
            )

        update_project_status(project_id, final_status.value.lower())
        transition_job(job_id, final_status)
        logger.info(
            "Worker indexing completed job_id=%s project_id=%s status=%s "
            "total_chunks=%s",
            job_id,
            project_id,
            final_status.value,
            index_result.total_chunks,
        )
        return {"job_id": job_id, "status": final_status.value}
    except Exception as exc:
        retry_or_fail_job(
            self,
            job_id=job_id,
            project_id=project_id,
            exc=exc,
            error_code="INDEXING_FAILED",
            fallback_message="Background evidence indexing failed.",
        )
        raise AssertionError("retry_or_fail_job must raise")

