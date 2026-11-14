"""Flag uncertain work for review. Elapsed time never proves a refundable failure."""
from datetime import datetime,UTC,timedelta
from sqlalchemy import select
from app.db.models.account import ProviderOperation,AnalysisReservation
from app.services.account_usage import event


def mark_uncertain_operations(session,*,now=None,after_seconds=600,limit=100):
    now=now or datetime.now(UTC)
    rows=session.scalars(select(ProviderOperation).where(ProviderOperation.state.in_(["admitted","running"]),ProviderOperation.created_at<now-timedelta(seconds=max(600,after_seconds))).limit(min(100,limit)).with_for_update(skip_locked=True)).all()
    for operation in rows:
        operation.state="needs_reconciliation"
        if operation.provider_details:
            operation.provider_details=dict(operation.provider_details,settlement="needs_reconciliation",cost_status="unknown_outcome_reserved",estimated_cost_usd=None)
        reservation=session.get(AnalysisReservation,operation.reservation_id)
        if reservation and reservation.state in {"reserved","processing"}:
            reservation.state="needs_reconciliation"
            if operation.kind in {"extraction","extraction_metadata"}:
                _fail_stalled_ingestion(session,reservation)
        event(session,operation.user_id,"provider_needs_reconciliation",operation.id,{"reason":"No confirmed outcome within the review interval; no refund or paid replay."})
    # A crash after the worker claim but before the first provider admission also
    # needs durable review; duplicate outbox delivery must never replay that work.
    from app.db.models.account import DispatchOutbox,UsageEvent
    claims=session.scalars(select(UsageEvent).where(UsageEvent.kind=="ingestion_claimed",UsageEvent.created_at<now-timedelta(seconds=max(600,after_seconds))).limit(min(100,limit))).all()
    for claim in claims:
        outbox=session.get(DispatchOutbox,claim.reference_id)
        reservation=session.get(AnalysisReservation,outbox.reservation_id) if outbox else None
        if outbox and outbox.state=="claimed" and reservation and reservation.state=="processing" and not session.get(DispatchOutbox,"index:"+outbox.id):
            reservation.state="needs_reconciliation"
            _fail_stalled_ingestion(session,reservation)
            event(session,reservation.user_id,"ingestion_needs_reconciliation",outbox.id,{"reason":"Claimed ingestion did not durably hand off to indexing; no automatic replay."})
    return len(rows)


def _fail_stalled_ingestion(session,reservation):
    from app.db.models.ingestion_job import IngestionJob
    from app.db.repositories.job_repository import JobRepository
    job=session.get(IngestionJob,reservation.job_id) if reservation.job_id else None
    if job and job.project_id==reservation.project_id and job.status not in {"READY","PARTIAL_READY","FAILED"}:
        JobRepository(session).fail(job.id,error_code="NEEDS_RECONCILIATION",error_message="Stalled extraction requires provider/worker review; no automatic paid replay or credit refund.")
