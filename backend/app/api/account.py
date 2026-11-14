from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from app.core.access import require_principal,owned_project,insert_once
from app.db.models.account import AppUser,UsageEvent,RevokedSession,AnalysisReservation,ProviderOperation
from app.db.session import database_session
from app.db.repositories._utils import utc_now
from app.services.account_usage import balance,latest_reservation,complete_owned_analysis

router=APIRouter(tags=["Account and usage"])


@router.get("/api/account")
def account():
    principal=require_principal()
    with database_session() as session:
        user=session.get(AppUser,principal.user_id)
        return {"id":user.id,"email":user.email,"display_name":user.display_name,"avatar_url":user.avatar_url,"role":user.role,"plan":"free","usage":balance(session,user.id)}


@router.get("/api/account/usage")
def usage():
    principal=require_principal()
    with database_session() as session:
        events=session.scalars(select(UsageEvent).where(UsageEvent.user_id==principal.user_id).order_by(UsageEvent.created_at.desc()).limit(50)).all()
        reservations=session.scalars(select(AnalysisReservation).where(AnalysisReservation.user_id==principal.user_id).order_by(AnalysisReservation.created_at.desc()).limit(50)).all()
        return {"balance":balance(session,principal.user_id),"events":[{"kind":e.kind,"reference_id":e.reference_id,"created_at":e.created_at} for e in events],"analyses":[{"id":r.id,"project_id":r.project_id,"state":r.state,"completion_mode":r.completion_mode} for r in reservations]}


@router.post("/api/account/logout")
def logout():
    principal=require_principal()
    with database_session() as session:
        insert_once(session,RevokedSession,{"id":principal.session_id,"user_id":principal.user_id,"created_at":utc_now()},"id")
    return {"status":"signed_out"}


class CompletionRequest(BaseModel):
    metrics_only:bool=False


@router.post("/api/projects/{project_id}/complete")
def complete(project_id:str,payload:CompletionRequest):
    principal=require_principal()
    with database_session() as session:
        value=complete_owned_analysis(session,principal,project_id,payload.metrics_only)
        return {"state":value.state,"completion_mode":value.completion_mode,"usage":balance(session,principal.user_id)}


@router.get("/api/projects/{project_id}/usage")
def project_usage(project_id:str):
    principal=require_principal()
    with database_session() as session:
        owned_project(session,project_id,principal)
        reservation=latest_reservation(session,project_id)
        operations=session.scalars(select(ProviderOperation).where(ProviderOperation.project_id==project_id,ProviderOperation.user_id==principal.user_id)).all()
        return {"analysis_state":reservation.state if reservation else "not_started","completion_mode":reservation.completion_mode if reservation else None,"assistant_remaining":max(0,3-sum(op.kind=="assistant" for op in operations if reservation and op.reservation_id==reservation.id)),"semantic_remaining":{slot:max(0,2-sum(op.kind=="semantic" and op.slot==slot for op in operations if reservation and op.reservation_id==reservation.id)) for slot in ("content_1","content_2")}}
