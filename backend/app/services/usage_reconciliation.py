"""Flag uncertain work for review. Elapsed time never proves a refundable failure."""
from datetime import datetime,UTC,timedelta
from sqlalchemy import select
from app.db.models.account import ProviderOperation,AnalysisReservation
from app.services.account_usage import event


def mark_uncertain_operations(session,*,now=None,after_seconds=600,limit=100):
    now=now or datetime.now(UTC)
    rows=session.scalars(select(ProviderOperation).where(ProviderOperation.state=="admitted",ProviderOperation.created_at<now-timedelta(seconds=max(600,after_seconds))).limit(min(100,limit)).with_for_update(skip_locked=True)).all()
    for operation in rows:
        operation.state="needs_reconciliation"
        reservation=session.get(AnalysisReservation,operation.reservation_id)
        if reservation and reservation.state in {"reserved","processing"}:reservation.state="needs_reconciliation"
        event(session,operation.user_id,"provider_needs_reconciliation",operation.id,{"reason":"No confirmed outcome within the review interval; no refund or paid replay."})
    return len(rows)
