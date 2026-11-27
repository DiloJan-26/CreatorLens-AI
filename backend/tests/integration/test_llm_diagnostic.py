"""Engineering diagnostics through real auth, admission, tracking and SQL; mocked SDK only."""
from contextlib import contextmanager
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import select, func
from app.db.models.account import ProviderOperation, BudgetAccount
from app.db.models.llm_observability import LlmRun
from app.services.account_usage import reserve, settle
from tests.integration.test_engineering_boundary import boundary, headers, unlock  # noqa: F401


@pytest.fixture
def diagnostic(boundary,monkeypatch):
    from app.services import llm_diagnostic_service as service, provider_admission as admission
    client,settings,redis,a,b,project,session=boundary
    settings.provider_emergency_stop=False;settings.gemini_api_key="offline-sdk-fixture"
    settings.llm_cache_billing_mode="implicit"
    calls=[]
    @contextmanager
    def database():yield session;session.flush()
    monkeypatch.setattr(service,"get_settings",lambda:settings)
    monkeypatch.setattr(admission,"get_settings",lambda:settings)
    monkeypatch.setattr(admission,"database_session",database)
    monkeypatch.setattr(admission,"enforce_rate",lambda *a:None)
    from app.llm.pricing_policy import load_pricing_registry, resolve_price
    from datetime import date
    price=resolve_price(load_pricing_registry(),settings.llm_provider,settings.llm_model,"standard",date(2026,11,27))
    assert price
    monkeypatch.setattr(admission,"resolve_price",lambda *a:price)
    class Model:
        async def ainvoke(self,prompt):
            calls.append(prompt)
            assert admission.active_operation.get()
            return SimpleNamespace(content="OK",usage_metadata={"input_tokens":4,"output_tokens":1,"total_tokens":5,"input_token_details":{"cache_read":0}})
    def factory(**kwargs):
        assert kwargs["max_retries"]==0 and kwargs["timeout"]<=15 and kwargs["max_output_tokens"]<=80
        return Model()
    monkeypatch.setattr(service,"get_llm",factory)
    r,_=reserve(session,b,project,"diagnostic-fixture")
    settle(session,r.id,"completed",completion_mode="deterministic")
    yield (*boundary,calls,service)


def check(client,project,user="b",**extra):
    return client.post("/api/engineering/llm-check",headers=headers(user),json={"project_id":project,**extra})


def test_check_requires_auth_unlock_owned_completed_project(diagnostic):
    client,settings,redis,a,b,project,session,calls,service=diagnostic
    assert client.post("/api/engineering/llm-check",json={"project_id":project}).status_code==401
    assert check(client,project).status_code==403
    unlock(client,"a");assert check(client,project,"a").status_code==404
    unlock(client,"b")
    assert client.get("/api/engineering/llm-check",headers=headers("b")).status_code==405
    assert check(client,project,prompt="arbitrary prompt").status_code==422
    assert check(client,"not-an-id").status_code==422
    assert calls==[]


def test_success_separate_diagnostic_tracked_once_no_assistant_usage(diagnostic):
    client,settings,redis,a,b,project,session,calls,service=diagnostic;unlock(client,"b")
    response=check(client,project);value=response.json()
    assert response.status_code==200 and value["status"]=="reachable",value
    assert value["provider_invocation_count"]==1 and "generated_text" not in value
    assert response.headers["Cache-Control"]=="private, no-store"
    assert calls==["Reply with OK."]
    op=session.scalar(select(ProviderOperation));assert op.kind=="diagnostic" and op.state=="completed"
    assert op.provider_details["model"]==settings.llm_model
    assert session.get(BudgetAccount,b.user_id).reserved_usd==settings.provider_operation_ceiling_usd
    runs=session.scalars(select(LlmRun)).all()
    assert len(runs)==1 and runs[0].project_id==project and runs[0].operation_type=="diagnostic_generation"
    assert runs[0].provider_invocation_count==1
    from app.db.models.llm_observability import CostEvent
    cost=session.scalar(select(CostEvent));assert cost and cost.project_id==project and cost.estimated_cost_usd is not None
    assert session.scalar(select(func.count()).select_from(ProviderOperation).where(ProviderOperation.kind=="assistant"))==0
    assert check(client,project).json()["status"]=="blocked" and len(calls)==1
    assert session.scalar(select(func.count()).select_from(ProviderOperation))==1


@pytest.mark.parametrize("blocked",["emergency","budget","pricing","allowance","incomplete"])
def test_local_denial_never_calls_provider_or_creates_model_run(diagnostic,monkeypatch,blocked):
    from app.services import provider_admission as admission
    from app.db.models.account import AnalysisReservation
    client,settings,redis,a,b,project,session,calls,service=diagnostic;unlock(client,"b")
    if blocked=="emergency":settings.provider_emergency_stop=True
    if blocked=="budget":settings.global_budget_usd=0
    if blocked=="pricing":monkeypatch.setattr(admission,"resolve_price",lambda *a:None)
    if blocked=="allowance":settings.diagnostic_attempts_per_analysis=0
    if blocked=="incomplete":session.scalar(select(AnalysisReservation)).state="processing";session.flush()
    value=check(client,project).json()
    assert value["status"]=="blocked" and value["provider_invocation_count"]==0
    assert "down" not in value["message"].lower() and calls==[]
    assert session.scalar(select(func.count()).select_from(LlmRun))==0
    assert session.scalar(select(func.count()).select_from(ProviderOperation))==0


@pytest.mark.parametrize("mode,reason",[("timeout","timeout"),("quota","provider_limit"),("access","provider_access"),("empty","provider_error"),("unexpected","unexpected_response")])
def test_provider_failure_safe_classification_and_accounting(diagnostic,monkeypatch,mode,reason):
    client,settings,redis,a,b,project,session,calls,service=diagnostic;unlock(client,"b")
    class ProviderError(Exception):status_code=429 if mode=="quota" else 403
    class Model:
        async def ainvoke(self,prompt):
            calls.append(prompt)
            if mode=="timeout":raise TimeoutError("SECRET provider detail")
            if mode in {"quota","access"}:raise ProviderError("SECRET credential detail")
            return SimpleNamespace(content="" if mode=="empty" else "unexpected answer")
    monkeypatch.setattr(service,"get_llm",lambda **kwargs:Model())
    value=check(client,project).json()
    assert value["status"]=="failed" and value["reason"]==reason and value["provider_invocation_count"]==1
    assert "SECRET" not in str(value) and len(calls)==1
    run=session.scalar(select(LlmRun));assert run.provider_invocation_count==1
    op=session.scalar(select(ProviderOperation))
    assert op.state==("completed" if mode=="unexpected" else "needs_reconciliation")
    if mode!="unexpected":assert check(client,project).json()["status"]=="blocked" and len(calls)==1


def test_fixed_attempt_limit_after_cooldown_and_locked_reads_do_not_infer(diagnostic):
    client,settings,redis,a,b,project,session,calls,service=diagnostic;unlock(client,"b")
    for n in range(3):
        assert check(client,project).json()["status"]=="reachable"
        op=session.scalar(select(ProviderOperation).order_by(ProviderOperation.created_at.desc()))
        op.created_at=datetime.now(UTC)-timedelta(seconds=65*(3-n));session.flush()
    assert check(client,project).json()["status"]=="blocked" and len(calls)==3
    client.get("/api/engineering/access",headers=headers("b"))
    client.get("/api/metrics/cost?project_id="+project,headers=headers("b"))
    client.get("/api/evaluations/datasets",headers=headers("b"))
    assert len(calls)==3
    client.post("/api/engineering/lock",headers=headers("b"))
    assert check(client,project).status_code==403 and len(calls)==3

