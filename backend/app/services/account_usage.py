"""Transactional credit accounting; no refund or external call inside a DB lock."""
from hashlib import sha256
from uuid import uuid4
from sqlalchemy import select, func
from fastapi import HTTPException
from app.db.models.account import AppUser, UserEntitlement, AnalysisReservation, UsageEvent, ProviderOperation, DispatchOutbox, ACTIVE_STATES
from app.db.repositories._utils import utc_now
from app.core.access import owned_project, insert_once


def event(session, user_id, kind, reference, details=None):
    insert_once(session,UsageEvent,dict(id=str(uuid4()),user_id=user_id,event_key=kind+":"+reference,kind=kind,reference_id=reference,details=details or {},created_at=utc_now()),"event_key")


def balance(session,user_id):
    entitlement=session.get(UserEntitlement,user_id)
    if entitlement is None: raise HTTPException(403,"Account entitlement is unavailable.")
    return dict(granted=entitlement.granted,completed=entitlement.consumed,reserved=entitlement.reserved,available=entitlement.granted-entitlement.consumed-entitlement.reserved)


def reserve(session,principal,project_id,idempotency_key):
    if not idempotency_key or not 8 <= len(idempotency_key) <= 128:
        raise HTTPException(422,"An 8-128 character Idempotency-Key is required.")
    project=owned_project(session,project_id,principal)
    entitlement=session.scalar(select(UserEntitlement).where(UserEntitlement.user_id==principal.user_id).with_for_update())
    if not entitlement: raise HTTPException(403,"No entitlement.")
    fingerprint=sha256((project.id+"\n"+project.content_1_url+"\n"+project.content_2_url).encode()).hexdigest()
    existing=session.scalar(select(AnalysisReservation).where(AnalysisReservation.user_id==principal.user_id,AnalysisReservation.idempotency_key==idempotency_key))
    if existing:
        if existing.fingerprint != fingerprint: raise HTTPException(409,"Idempotency key belongs to a different analysis.")
        return existing,False
    if session.scalar(select(AnalysisReservation.id).where(AnalysisReservation.user_id==principal.user_id,AnalysisReservation.state.in_(ACTIVE_STATES))):
        raise HTTPException(409,"One analysis is already active. Reopen it or reconcile its status.")
    if entitlement.consumed+entitlement.reserved >= 5:
        raise HTTPException(403,{"code":"analysis_limit_reached","message":"Free analysis limit reached"})
    entitlement.reserved+=1
    reservation=AnalysisReservation(id=str(uuid4()),user_id=principal.user_id,project_id=project_id,idempotency_key=idempotency_key,fingerprint=fingerprint,state="reserved")
    session.add(reservation);session.flush()
    event(session,principal.user_id,"analysis_reserved",reservation.id)
    return reservation,True


def latest_reservation(session,project_id):
    return session.scalar(select(AnalysisReservation).where(AnalysisReservation.project_id==project_id).order_by(AnalysisReservation.created_at.desc()).limit(1))


def settle(session,reservation_id,target,*,completion_mode=None,verified_no_active_work=False):
    reservation=session.get(AnalysisReservation,reservation_id)
    if reservation is None: raise HTTPException(404,"Reservation not found.")
    entitlement=session.scalar(select(UserEntitlement).where(UserEntitlement.user_id==reservation.user_id).with_for_update())
    session.refresh(reservation)
    if reservation.state not in ACTIVE_STATES: return reservation
    if target == "needs_reconciliation":
        reservation.state=target
    elif target == "completed":
        if completion_mode not in {"semantic","metrics_only"}: raise HTTPException(409,"An explicit completion mode is required.")
        if session.scalar(select(ProviderOperation.id).where(ProviderOperation.reservation_id==reservation.id,ProviderOperation.state.in_(["admitted","running","needs_reconciliation"]))):
            raise HTTPException(409,"Provider work must settle before completion.")
        entitlement.reserved-=1;entitlement.consumed+=1
        reservation.state=target;reservation.completion_mode=completion_mode
    elif target in {"failed","cancelled","expired"}:
        operations=session.scalars(select(ProviderOperation).where(ProviderOperation.reservation_id==reservation.id)).all()
        if not verified_no_active_work or any(op.state in {"admitted","running","needs_reconciliation"} for op in operations):
            raise HTTPException(409,"Work/provider outcomes require reconciliation before releasing a credit.")
        entitlement.reserved-=1;reservation.state=target
    else: raise HTTPException(422,"Invalid settlement.")
    reservation.updated_at=utc_now()
    event(session,reservation.user_id,"analysis_"+target,reservation.id,{"completion_mode":completion_mode})
    session.flush();return reservation


def complete_owned_analysis(session,principal,project_id,metrics_only):
    project=owned_project(session,project_id,principal)
    reservation=latest_reservation(session,project_id)
    if not reservation or reservation.user_id != principal.user_id: raise HTTPException(404,"Reservation not found.")
    if reservation.job_id:
        from app.db.models.ingestion_job import IngestionJob
        job=session.get(IngestionJob,reservation.job_id)
        if not job or job.project_id!=project_id or job.status not in {"READY","PARTIAL_READY"}:
            raise HTTPException(409,"Wait for the admitted ingestion job to finish before completing this analysis.")
    # Only terminal ingestion plus validated persisted evidence can complete.
    from app.db.models.content_item import ContentItem
    from app.db.repositories.metadata_repository import MetadataRepository
    items=session.scalars(select(ContentItem).where(ContentItem.project_id==project_id)).all()
    if project.status.lower() not in {"ready","partial_ready"} or len(items)!=2 or {item.slot for item in items}!={"content_1","content_2"} or any(item.extraction_status not in {"ready","partial"} for item in items):
        raise HTTPException(409,"Both content items must have usable evidence after ingestion.")
    from math import isfinite
    from app.services.evidence_quality import EVIDENCE_POLICY_VERSION
    snapshots={item.id:MetadataRepository(session).latest_for_item(item.id) for item in items}
    for item in items:
        snapshot=snapshots[item.id]
        raw=snapshot.raw_payload if snapshot else {}
        views=raw.get("views")
        confirmed_views=not isinstance(views,bool) and isinstance(views,(int,float)) and isfinite(views) and views>=0 and int(views)==views
        evidence=raw.get("transcript_evidence") or {}
        validated_transcript=bool(item.transcript_available and item.transcript_segment_count>0 and evidence.get("policy_version")==EVIDENCE_POLICY_VERSION and evidence.get("status") in {"valid","partial"})
        if not confirmed_views and not validated_transcript:
            raise HTTPException(409,"Each content needs usable validated transcript evidence or confirmed public views; a partial status alone cannot complete an analysis.")
    from app.services.semantic_service import get_semantic_analysis
    semantic=[get_semantic_analysis(project_id,item.slot) for item in items] if not metrics_only else []
    if not metrics_only and any(result["status"] not in {"ready","unavailable"} or result["status"]=="unavailable" and result.get("error_code")!="EVIDENCE_UNAVAILABLE" for result in semantic):
        raise HTTPException(409,"Semantic analysis is not complete. Review metrics-only completion if sufficient metrics exist.")
    if metrics_only:
        for item in items:
            snapshot=snapshots[item.id]
            raw=snapshot.raw_payload if snapshot else {}
            views=raw.get("views")
            from math import isfinite
            if isinstance(views,bool) or not isinstance(views,(int,float)) or not isfinite(views) or views<0 or int(views)!=views:
                raise HTTPException(409,"Metrics-only completion requires confirmed views for both contents.")
    elif any(not item.transcript_available for item in items) and not all(result["status"]=="unavailable" and result.get("error_code")=="EVIDENCE_UNAVAILABLE" for result in semantic):
        raise HTTPException(409,"Validated transcript evidence is required for semantic completion.")
    operations=session.scalars(select(ProviderOperation).where(ProviderOperation.reservation_id==reservation.id)).all()
    if any(op.state in {"admitted","running","needs_reconciliation"} for op in operations):
        raise HTTPException(409,"Provider operations must settle before analysis completion.")
    return settle(session,reservation.id,"completed",completion_mode="metrics_only" if metrics_only else "semantic")
