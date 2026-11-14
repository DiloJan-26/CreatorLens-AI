"""Reload authoritative ownership before work; no JWT/user ID in task payloads."""
from functools import wraps
from uuid import uuid4
from sqlalchemy import select
from celery.exceptions import Reject
from app.core.config import get_settings
from app.core.identity import Principal
from app.core.access import current_principal,owned_project
from app.db.session import database_session
from app.db.models.account import AppUser,AnalysisReservation,DispatchOutbox
from app.db.models.ingestion_job import IngestionJob
from app.db.models.semantic_snapshot import SemanticSnapshot
from app.services.account_usage import latest_reservation
from app.services.provider_admission import admit,finish,operation_scope


def owned_task(kind):
    def decorate(function):
        @wraps(function)
        def execute(*args,**kwargs):
            if get_settings().application_access_mode!="authenticated":return function(*args,**kwargs)
            identifier=kwargs.get("snapshot_id" if kind=="semantic" else "job_id") or args[-1]
            operation=None
            with database_session() as session:
                resource=session.get(SemanticSnapshot if kind=="semantic" else IngestionJob,identifier)
                if resource is None:raise Reject("Unknown persisted work.",requeue=False)
                reservation=latest_reservation(session,resource.project_id)
                user=session.get(AppUser,reservation.user_id) if reservation else None
                if not user or user.status!="active" or reservation.state not in {"reserved","processing"}:
                    raise Reject("Work is no longer authorized; reconcile its reservation.",requeue=False)
                principal=Principal(user.id,str(uuid4()),0)
                owned_project(session,resource.project_id,principal)
                if kind=="semantic":
                    from app.db.models.content_item import ContentItem
                    item=session.get(ContentItem,resource.content_id)
                    if not item or item.project_id!=resource.project_id or item.slot!=resource.slot:
                        raise Reject("Semantic content membership mismatch.",requeue=False)
                    if resource.status in {"ready","unavailable"}:return {"status":resource.status}
                    if resource.status!="pending":return {"status":"deduplicated"}
                    operation=admit(session,principal,resource.project_id,"semantic",slot=resource.slot,snapshot_id=identifier)
                else:
                    if reservation.job_id!=identifier:raise Reject("Stale job identity.",requeue=False)
                    if str(resource.status).upper() in {"READY","PARTIAL_READY","FAILED"}:return {"status":resource.status}
                    if kind=="extraction":
                        outbox=session.scalar(select(DispatchOutbox).where(DispatchOutbox.id==identifier).with_for_update())
                        if not outbox or outbox.reservation_id!=reservation.id or outbox.task_name!="creatorlens.ingest_project" or outbox.argument!=identifier:
                            raise Reject("Missing authoritative ingestion outbox.",requeue=False)
                        if outbox.state=="claimed":return {"status":"deduplicated"}
                        if outbox.state not in {"pending","sent"}:return {"status":"deduplicated"}
                        from app.services.provider_admission import paid_configuration
                        paid_configuration(get_settings(),"extraction")
                        outbox.state="claimed"
                        from app.services.account_usage import event
                        event(session,user.id,"ingestion_claimed",identifier)
                reservation.state="processing"
                outbox=session.get(DispatchOutbox,identifier)
                if outbox:outbox.state="claimed"
            handle=current_principal.set(principal)
            try:
                with operation_scope(operation):
                    result=function(*args,**kwargs)
                known=not isinstance(result,dict) or result.get("error_code") not in {"SEMANTIC_TIMEOUT","SEMANTIC_EXTRACTION_FAILED","SEMANTIC_RATE_LIMIT"}
                finish(operation,known_response=known)
                return result
            except BaseException:
                finish(operation,known_response=False)
                raise
            finally:current_principal.reset(handle)
        return execute
    return decorate


def queue_index(reservation,job_id):
    identifier="index:"+job_id
    with database_session() as session:
        if session.get(DispatchOutbox,identifier) is None:
            session.add(DispatchOutbox(id=identifier,reservation_id=reservation,task_name="creatorlens.index_project",argument=job_id,state="pending"))
    from app.workers.dispatch_outbox import dispatch
    dispatch(only_id=identifier)
