"""Atomic post-index completion with isolated SQL; providers are never invoked."""
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.access import current_principal
from app.db.models.account import ProviderOperation, UsageEvent
from app.db.models.project import Project
from app.db.repositories.job_repository import JobRepository
from app.db.repositories.content_item_repository import ContentItemRepository
from app.db.repositories.metadata_repository import MetadataRepository
from app.models.video import VideoMetadata
from app.schemas.ingestion import IngestionJobStatus
from app.services import account_usage, provider_admission
from app.workers import job_runtime
from tests.unit.test_account_entitlements import account, project


@pytest.fixture
def indexed(db_session, monkeypatch):
    principal=account(db_session); pid=project(db_session,principal)
    reservation,_=account_usage.reserve(db_session,principal,pid,"auto-completion")
    job=JobRepository(db_session).create(pid);reservation.job_id=job.id
    job.status="INDEXING";db_session.get(Project,pid).status="indexing"
    for slot in ("content_1","content_2"):
        item=ContentItemRepository(db_session).upsert(project_id=pid,slot=slot,platform="youtube",url="https://youtu.be/"+slot,extraction_status="partial",transcript_available=False,transcript_segment_count=0)
        MetadataRepository(db_session).create_snapshot(content_item=item,metadata=VideoMetadata(platform="youtube",slot=slot,url=item.url,views=1000,extraction_status="partial"))
    db_session.flush()
    @contextmanager
    def database():
        with db_session.begin_nested():yield db_session
    monkeypatch.setattr(job_runtime,"database_session",database)
    handle=current_principal.set(principal)
    try:yield principal,pid,reservation,job
    finally:current_principal.reset(handle)


@pytest.mark.parametrize("target",[IngestionJobStatus.READY,IngestionJobStatus.PARTIAL_READY])
def test_index_completion_settles_once_and_opens_assistant_admission(db_session,monkeypatch,indexed,target):
    principal,pid,reservation,job=indexed
    monkeypatch.setattr(provider_admission,"paid_configuration",lambda *a:Decimal(".01"))
    job_runtime.complete_indexed_job(job.id,pid,target)
    assert job.status==target.value and db_session.get(Project,pid).status==target.value.lower()
    assert reservation.state=="completed" and reservation.completion_mode=="deterministic"
    expected=dict(granted=5,completed=1,reserved=0,available=4)
    assert account_usage.balance(db_session,principal.user_id)==expected
    job_runtime.complete_indexed_job(job.id,pid,target)
    account_usage.complete_owned_analysis(db_session,principal,pid,False)
    assert account_usage.balance(db_session,principal.user_id)==expected
    assert db_session.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.reference_id==reservation.id,UsageEvent.kind=="analysis_completed"))==1
    assert not db_session.scalar(select(ProviderOperation.id).where(ProviderOperation.project_id==pid))
    # Admission only: no model request; existing limits and quota remain authoritative.
    settings=SimpleNamespace(user_budget_usd="1",global_budget_usd="2",assistant_admissions_per_analysis=3,llm_provider="gemini",llm_model="gemini-3.5-flash-lite",llm_estimate_service_tier="standard")
    identifier=provider_admission.admit(db_session,principal,pid,"assistant",settings=settings,rate=False)
    assert db_session.get(ProviderOperation,identifier).kind=="assistant"
    next_pid=project(db_session,principal)
    account_usage.reserve(db_session,principal,next_pid,"next-analysis")
    assert account_usage.balance(db_session,principal.user_id)["reserved"]==1


@pytest.mark.parametrize("state",["admitted","running","needs_reconciliation"])
def test_unsettled_provider_work_rolls_back_all_completion_state(db_session,indexed,state):
    principal,pid,reservation,job=indexed
    db_session.add(ProviderOperation(id=str(uuid4()),reservation_id=reservation.id,project_id=pid,user_id=principal.user_id,kind="extraction",slot="content_2",attempt=1,state=state,ceiling_usd=Decimal(".05")))
    db_session.flush()
    with pytest.raises(HTTPException):job_runtime.complete_indexed_job(job.id,pid,IngestionJobStatus.PARTIAL_READY)
    assert job.status=="INDEXING" and db_session.get(Project,pid).status=="indexing"
    assert reservation.state=="reserved" and account_usage.balance(db_session,principal.user_id)["completed"]==0
    assert not db_session.scalar(select(UsageEvent.id).where(UsageEvent.reference_id==reservation.id,UsageEvent.kind=="analysis_completed"))


@pytest.mark.parametrize("state",["failed","cancelled","needs_reconciliation"])
def test_closed_or_unresolved_analysis_cannot_auto_complete(db_session,indexed,state):
    principal,pid,reservation,job=indexed;reservation.state=state;db_session.flush()
    with pytest.raises(HTTPException):job_runtime.complete_indexed_job(job.id,pid,IngestionJobStatus.PARTIAL_READY)
    with pytest.raises(HTTPException):account_usage.complete_owned_analysis(db_session,principal,pid,False)
    assert job.status=="INDEXING" and account_usage.balance(db_session,principal.user_id)["completed"]==0


@pytest.mark.parametrize("damage",["missing_content","empty_metrics","failed_job","stale_job","wrong_owner"])
def test_completion_requires_current_owned_job_and_usable_evidence(db_session,indexed,damage):
    principal,pid,reservation,job=indexed
    if damage=="missing_content":
        item=ContentItemRepository(db_session).get_model_by_slot(pid,"content_2");db_session.delete(item)
    elif damage=="empty_metrics":
        item=ContentItemRepository(db_session).get_model_by_slot(pid,"content_2")
        MetadataRepository(db_session).create_snapshot(content_item=item,metadata=VideoMetadata(platform="youtube",slot="content_2",url=item.url,extraction_status="partial"))
    elif damage=="failed_job":job.status="FAILED"
    elif damage=="stale_job":reservation.job_id="other-job"
    else:db_session.get(Project,pid).owner_user_id=account(db_session).user_id
    db_session.flush()
    before_job=job.status
    with pytest.raises((HTTPException,ValueError)):job_runtime.complete_indexed_job(job.id,pid,IngestionJobStatus.PARTIAL_READY)
    assert job.status==before_job and account_usage.balance(db_session,principal.user_id)["completed"]==0
