"""Reserve credit, job and outbox atomically before any broker publication."""
from uuid import uuid4
from app.core.access import require_principal
from app.core.config import get_settings
from app.core.request_limits import enforce_rate
from app.db.session import database_session
from app.db.models.account import DispatchOutbox
from app.db.repositories.job_repository import JobRepository
from app.services.account_usage import reserve
from app.services.provider_admission import paid_configuration
from app.schemas.ingestion import IngestionStartResponse,IngestionJobStatus


def start(project_id,key):
    settings=get_settings();principal=require_principal()
    paid_configuration(settings,"extraction")
    enforce_rate(settings,principal.user_id,"analysis")
    with database_session() as session:
        reservation,created=reserve(session,principal,project_id,key)
        if created:
            job=JobRepository(session).create(project_id)
            reservation.job_id=job.id
            JobRepository(session).set_task_id(job.id,job.id)
            session.add(DispatchOutbox(id=job.id,reservation_id=reservation.id,task_name="creatorlens.ingest_project",argument=job.id,state="pending"))
        job_id=reservation.job_id
        existing_job=JobRepository(session).get(job_id) if job_id else None
        job_status=IngestionJobStatus(existing_job.status) if existing_job else IngestionJobStatus.PENDING
    if not job_id:raise RuntimeError("Accepted analysis has no durable job identity.")
    from app.workers.dispatch_outbox import dispatch
    dispatch(only_id=job_id)
    return IngestionStartResponse(project_id=project_id,job_id=job_id,status=job_status,status_url=f"/api/projects/{project_id}/status?job_id={job_id}",message="Analysis admitted. Dispatch is durable; retry the same Idempotency-Key if the broker is unavailable.")
