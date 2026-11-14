"""Bounded outbox relay. Safe stable-ID redelivery; provider admission deduplicates work."""
from sqlalchemy import select
from app.db.session import database_session
from app.db.models.account import DispatchOutbox,AnalysisReservation,AppUser


def dispatch(only_id=None,limit=20):
    from app.workers.celery_app import celery_app
    published=0
    with database_session() as session:
        from app.services.usage_reconciliation import mark_uncertain_operations
        mark_uncertain_operations(session)
        query=select(DispatchOutbox).where(DispatchOutbox.state.in_(["pending","sent"]),DispatchOutbox.attempts<5)
        if only_id:query=query.where(DispatchOutbox.id==only_id)
        rows=session.scalars(query.order_by(DispatchOutbox.created_at).limit(min(limit,100)).with_for_update(skip_locked=True)).all()
        for row in rows:
            reservation=session.get(AnalysisReservation,row.reservation_id)
            user=session.get(AppUser,reservation.user_id) if reservation else None
            if not user or user.status!="active" or reservation.state not in {"reserved","processing"}:continue
            row.attempts+=1
            try:
                celery_app.send_task(row.task_name,args=[row.argument],task_id=row.id)
                row.state="sent";published+=1
            except Exception:row.state="pending"
    return published


if __name__=="__main__":
    print("Published outbox messages:",dispatch())
