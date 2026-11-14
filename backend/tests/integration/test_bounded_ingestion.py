"""Mocked HTTP -> real isolated repositories -> quota completion; no live services."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select
from app.core.access import provision,current_principal
from app.core.identity import Principal
from app.db.models.account import ProviderOperation,DispatchOutbox,BudgetAccount
from app.db.models.content_item import ContentItem
from app.db.repositories.project_repository import ProjectRepository
from app.db.repositories.job_repository import JobRepository
from app.db.repositories import storage_repository as storage
from app.services import project_service,metric_source_service,account_usage
from app.extraction import accounting,bounded_provider,policy


@pytest.mark.parametrize("captions",[True,False])
def test_two_slot_bounded_ingestion_persistence_and_metrics_completion(db_session,monkeypatch,captions):
    principal=Principal(str(uuid4()),str(uuid4()),1);provision(db_session,principal)
    handle=current_principal.set(principal)
    urls=["https://www.youtube.com/watch?v=bounded_first","https://www.youtube.com/watch?v=bounded_second"]
    s=SimpleNamespace(application_access_mode="authenticated",paid_operations_enabled=True,extraction_enabled=True,
        extraction_max_concurrent_operations=1,extraction_max_video_seconds=300,extraction_max_url_bytes=2048,
        extraction_max_response_bytes=16384,extraction_timeout_seconds=5,supadata_billing_tier="pro_monthly_prepaid",
        supadata_prepaid_verified=True,supadata_auto_recharge_disabled=True,supadata_api_key="offline-fixture",
        supadata_credit_pool="integration-fixture-pool",supadata_credit_limit=100,supadata_transcript_mode="native",
        provider_operation_ceiling_usd=".01",user_budget_usd="1",global_budget_usd="10",paid_requests_per_minute=12,
        transcript_language="en",transcript_fallback_language_list=lambda:["en"],evidence_cache_max_age_seconds=86400)
    @contextmanager
    def database():
        yield db_session
        db_session.flush()
    monkeypatch.setattr(storage,"database_session",database)
    monkeypatch.setattr(accounting,"database_session",database)
    monkeypatch.setattr(accounting,"get_settings",lambda:s)
    monkeypatch.setattr(accounting,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(bounded_provider,"get_settings",lambda:s)
    monkeypatch.setattr(bounded_provider,"enforce_provider_rate",lambda settings:None)
    monkeypatch.setattr(project_service,"get_settings",lambda:s)
    original=policy.configuration
    for module in (accounting,bounded_provider):monkeypatch.setattr(module,"configuration",lambda supplied:original(supplied,at=date(2026,11,14)))
    # Bind the existing SQLAlchemy repository adapters instead of the legacy local file store.
    for module in (project_service,metric_source_service):
        for name in vars(module).copy():
            if hasattr(storage,name) and callable(getattr(storage,name)):
                original_function=getattr(module,name)
                if callable(original_function) and getattr(original_function,"__module__","").startswith(("app.services.storage_service","app.db.repositories.storage_repository")):
                    monkeypatch.setattr(module,name,getattr(storage,name))
    transport_calls=[]
    def handler(request):
        transport_calls.append(request)
        url=request.url.params["url"];second=url==urls[1]
        if request.url.path.endswith("metadata"):
            body={"platform":"youtube","type":"video","url":url,"title":"Synthetic second" if second else "Synthetic first",
                  "media":{"duration":30},"stats":{"views":2000 if second else 1000,"likes":20,"comments":2}}
            return httpx.Response(200,stream=httpx.ByteStream(__import__("json").dumps(body).encode()))
        if not captions:return httpx.Response(404,stream=httpx.ByteStream(b""))
        body={"lang":"en","content":[{"text":"Synthetic evidence for the second item." if second else "Synthetic evidence for the first item.","offset":0,"duration":8000}]}
        return httpx.Response(200,stream=httpx.ByteStream(__import__("json").dumps(body).encode()))
    original_client=httpx.Client
    def client(**kwargs):kwargs["transport"]=httpx.MockTransport(handler);return original_client(**kwargs)
    monkeypatch.setattr(bounded_provider.httpx,"Client",client)
    try:
        project=ProjectRepository(db_session).create(project_id=str(uuid4()),content_1_url=urls[0],content_2_url=urls[1],content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
        reservation,_=account_usage.reserve(db_session,principal,project,"bounded-integration")
        job=JobRepository(db_session).create(project);reservation.job_id=job.id
        db_session.add(DispatchOutbox(id=job.id,reservation_id=reservation.id,task_name="creatorlens.ingest_project",argument=job.id,state="claimed"));db_session.flush()
        result=project_service.extract_project_videos(project)
        assert len(transport_calls)==4 and result.status=="ready"
        assert all(item.extraction_status=="partial" for item in result.content_items)
        assert [item.views for item in result.content_items]==[1000,2000]
        assert [item.transcript_available for item in result.content_items]==[captions,captions]
        items=db_session.scalars(select(ContentItem).where(ContentItem.project_id==project)).all()
        assert len(items)==2 and len({item.id for item in items})==2
        operations=db_session.scalars(select(ProviderOperation).where(ProviderOperation.project_id==project)).all()
        assert len(operations)==4 and sum(op.reserved_quantity for op in operations)==4
        assert db_session.get(BudgetAccount,principal.user_id).reserved_usd==Decimal(".04")
        from fastapi import HTTPException
        with pytest.raises(HTTPException,match="finish"):
            account_usage.complete_owned_analysis(db_session,principal,project,True)
        # Simulated terminal indexing state; no real vector service is contacted.
        job.status="PARTIAL_READY";db_session.flush()
        account_usage.complete_owned_analysis(db_session,principal,project,True)
        assert account_usage.balance(db_session,principal.user_id)=={"granted":5,"completed":1,"reserved":0,"available":4}
        assert all(op.provider_details["actual_billed_cost_usd"] is None for op in operations)
        if captions:
            project_service.extract_project_videos(project)
            assert len(transport_calls)==4, "Compatible persisted evidence must not cause another provider call."
    finally:current_principal.reset(handle)
