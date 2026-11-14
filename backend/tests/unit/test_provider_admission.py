from contextlib import contextmanager
from types import SimpleNamespace
from dataclasses import replace
from uuid import uuid4
from decimal import Decimal
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.core.access import provision,current_principal
from app.core.identity import Principal
from app.db.models.account import AppUser,BudgetAccount,ProviderOperation,DispatchOutbox
from app.db.repositories.project_repository import ProjectRepository
from app.services.account_usage import reserve,settle
from app.services.provider_admission import admit,paid_configuration


def setup(session,monkeypatch):
    settings=SimpleNamespace(paid_operations_enabled=True,provider_operation_ceiling_usd=".1",user_budget_usd="1",global_budget_usd="10",extraction_operation_bound_usd=".1",provider_input_byte_limit=8192,llm_provider="gemini",llm_model="gemini-3.5-flash-lite",llm_estimate_service_tier="standard",application_access_mode="authenticated")
    import app.services.provider_admission as module
    monkeypatch.setattr(module,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(module,"get_settings",lambda:settings)
    monkeypatch.setattr(module,"resolve_price",lambda *args:{"input_per_million":".30","output_per_million":"2.50"})
    a=Principal(str(uuid4()),str(uuid4()),1);provision(session,a)
    handle=current_principal.set(a)
    try:
        p=ProjectRepository(session).create(project_id=str(uuid4()),content_1_url="one",content_2_url="two",content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
    finally:current_principal.reset(handle)
    reservation,_=reserve(session,a,p,"request-1")
    return a,p,reservation,settings


def test_three_admitted_assistant_attempts_fourth_denied(db_session,monkeypatch):
    a,p,r,s=setup(db_session,monkeypatch)
    with pytest.raises(HTTPException):admit(db_session,a,p,"assistant",settings=s)
    settle(db_session,r.id,"completed",completion_mode="metrics_only")
    for _ in range(3):admit(db_session,a,p,"assistant",settings=s)
    with pytest.raises(HTTPException):admit(db_session,a,p,"assistant",settings=s)
    assert db_session.scalar(select(func.count()).select_from(ProviderOperation))==3
    assert db_session.get(BudgetAccount,a.user_id).reserved_usd==Decimal(".3")


def test_semantic_safe_retry_and_slot_bound(db_session,monkeypatch):
    a,p,r,s=setup(db_session,monkeypatch)
    first=admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    with pytest.raises(HTTPException):admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    db_session.get(ProviderOperation,first).state="completed";db_session.flush()
    admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    with pytest.raises(HTTPException):admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    assert admit(db_session,a,p,"semantic",slot="content_2",settings=s)


@pytest.mark.parametrize("change",[{"paid_operations_enabled":False},{"user_budget_usd":"0"},{"provider_operation_ceiling_usd":".000001"},{"provider_input_byte_limit":0}])
def test_budget_kill_switch_and_unknown_configuration(db_session,monkeypatch,change):
    a,p,r,s=setup(db_session,monkeypatch)
    for key,value in change.items():setattr(s,key,value)
    with pytest.raises(HTTPException):admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    assert db_session.scalar(select(func.count()).select_from(ProviderOperation))==0


def test_unknown_model_tier_or_extraction_cost_blocks(db_session,monkeypatch):
    a,p,r,s=setup(db_session,monkeypatch)
    import app.services.provider_admission as module
    monkeypatch.setattr(module,"resolve_price",lambda *args:None)
    with pytest.raises(HTTPException):paid_configuration(s,"semantic")
    s.extraction_operation_bound_usd="0"
    with pytest.raises(HTTPException):paid_configuration(s,"extraction")


def test_user_global_budget_and_suspension(db_session,monkeypatch):
    a,p,r,s=setup(db_session,monkeypatch)
    s.global_budget_usd=".1"
    admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    with pytest.raises(HTTPException):admit(db_session,a,p,"semantic",slot="content_2",settings=s)
    db_session.get(AppUser,a.user_id).status="suspended";db_session.flush()
    with pytest.raises(HTTPException):admit(db_session,a,p,"semantic",slot="content_2",settings=s)


def test_atomic_rate_limits_and_outage():
    from app.core.request_limits import enforce_rate
    settings=SimpleNamespace(authenticated_requests_per_minute=2,analysis_requests_per_minute=1,paid_requests_per_minute=1,redis_url=None)
    class FakeRedis:
        count=0
        def eval(self,*args):self.count+=1;return [self.count,42]
    redis=FakeRedis()
    enforce_rate(settings,"a",connection=redis);enforce_rate(settings,"a",connection=redis)
    with pytest.raises(HTTPException) as error:enforce_rate(settings,"a",connection=redis)
    assert error.value.status_code==429 and error.value.headers["Retry-After"]=="42"
    class Down:
        def eval(self,*args):raise ConnectionError()
    with pytest.raises(HTTPException) as error:enforce_rate(settings,"a",connection=Down())
    assert error.value.status_code==503


def test_durable_outbox_survives_broker_failure(db_session,monkeypatch):
    a,p,r,s=setup(db_session,monkeypatch)
    row=DispatchOutbox(id=str(uuid4()),reservation_id=r.id,task_name="creatorlens.ingest_project",argument="job",state="pending",attempts=0)
    db_session.add(row);db_session.flush()
    import app.workers.dispatch_outbox as relay
    from app.workers.celery_app import celery_app
    @contextmanager
    def database():yield db_session
    monkeypatch.setattr(relay,"database_session",database)
    monkeypatch.setattr(celery_app,"send_task",lambda *args,**kwargs:(_ for _ in ()).throw(ConnectionError()))
    assert relay.dispatch()==0
    assert row.state=="pending" and row.attempts==1
    calls=[]
    monkeypatch.setattr(celery_app,"send_task",lambda *args,**kwargs:calls.append(kwargs))
    assert relay.dispatch()==1 and row.state=="sent"
    assert calls[0]["task_id"]==row.id and calls[0]["args"]==["job"]


def test_worker_reloads_owner_account_and_reservation(db_session,monkeypatch):
    from app.workers import owned_execution as worker
    from app.db.repositories.job_repository import JobRepository
    from celery.exceptions import Reject
    a,p,r,s=setup(db_session,monkeypatch)
    job=JobRepository(db_session).create(p);r.job_id=job.id;db_session.flush()
    @contextmanager
    def database():yield db_session
    monkeypatch.setattr(worker,"database_session",database);monkeypatch.setattr(worker,"get_settings",lambda:s)
    observed=[]
    @worker.owned_task("index")
    def work(job_id):observed.append(current_principal.get().user_id);return {"status":"ready"}
    assert work(job.id)=={"status":"ready"} and observed==[a.user_id]
    db_session.get(AppUser,a.user_id).status="suspended";db_session.flush()
    with pytest.raises(Reject):work(job.id)
    db_session.get(AppUser,a.user_id).status="active";r.state="cancelled";db_session.flush()
    with pytest.raises(Reject):work(job.id)
    assert observed==[a.user_id]


def test_input_budget_and_no_unadmitted_client_creation(monkeypatch):
    import app.services.provider_admission as admission
    settings=SimpleNamespace(application_access_mode="authenticated",provider_input_byte_limit=10)
    monkeypatch.setattr(admission,"get_settings",lambda:settings)
    with pytest.raises(HTTPException):admission.check_input(["short"])
    with admission.operation_scope("durable-operation"):
        admission.check_input(["short"])
        with pytest.raises(HTTPException):admission.check_input(["far too long a message"])
    assert admission.active_operation.get() is None


def test_paid_extraction_cannot_be_enabled_with_an_unverified_dollar_ceiling(db_session,monkeypatch):
    a,p,r,s=setup(db_session,monkeypatch)
    s.provider_operation_ceiling_usd="1000";s.user_budget_usd="10000";s.global_budget_usd="100000"
    with pytest.raises(HTTPException) as error:admit(db_session,a,p,"extraction",settings=s)
    assert error.value.status_code==403 and "provider-specific" in error.value.detail
    assert db_session.scalar(select(func.count()).select_from(ProviderOperation))==0


def test_lost_operation_is_flagged_without_refund_or_paid_replay(db_session,monkeypatch):
    from datetime import datetime,UTC,timedelta
    from app.services.usage_reconciliation import mark_uncertain_operations
    from app.services.account_usage import balance
    a,p,r,s=setup(db_session,monkeypatch)
    identifier=admit(db_session,a,p,"semantic",slot="content_1",settings=s)
    operation=db_session.get(ProviderOperation,identifier)
    operation.created_at=datetime.now(UTC)-timedelta(minutes=20);db_session.flush()
    assert mark_uncertain_operations(db_session)==1
    assert operation.state=="needs_reconciliation" and r.state=="needs_reconciliation"
    assert balance(db_session,a.user_id)["reserved"]==1
    assert db_session.get(BudgetAccount,a.user_id).reserved_usd==Decimal(".1")
    with pytest.raises(HTTPException):admit(db_session,a,p,"semantic",slot="content_1",settings=s)
