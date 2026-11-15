"""Configuration changes exercise real admission and accounting, never live providers."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from app.core.config import Settings, get_settings
from app.core.active_pricing import active_registry


@pytest.fixture(autouse=True)
def settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def registry_envelope(kind="llm"):
    directory = "llm" if kind == "llm" else "extraction"
    data = json.loads((Path(__file__).parents[2]/"app"/directory/"pricing_registry.json").read_text())
    entry = next(row for row in data["entries"] if row["effective_from"] == "2026-11-14")
    entry = deepcopy(entry)
    entry["currency"] = "USD"
    if kind == "llm":
        entry["policy_version"] = "operator-review-example-1"
        entry["input_per_million"] = "1.00"
        data = {"version":"operator-review-example-1","entries":[entry]}
    else:
        entry["pricing_policy"] = "operator-review-example-1"
        entry["max_requests_per_second"] = "1"
        entry["effective_through"] = "2026-11-16"
        data = {"policy_version":"operator-review-example-1","entries":[entry]}
    return {"approval":{"approved":True,"approved_by":"offline-test","approved_on":"2026-11-14","change_reference":"test-only"},"registry":data}


def test_approved_environment_values_and_decimal_precision(monkeypatch):
    values={"INITIAL_FREE_ANALYSES":"5","CONCURRENT_ANALYSES_PER_USER":"1","ASSISTANT_ADMISSIONS_PER_ANALYSIS":"3","SEMANTIC_ATTEMPTS_PER_SLOT":"2","PAID_REQUESTS_PER_MINUTE":"12","EXTRACTION_MAX_VIDEO_SECONDS":"300","EXTRACTION_MAX_URL_BYTES":"2048","EXTRACTION_MAX_RESPONSE_BYTES":"2097152","EXTRACTION_TIMEOUT_SECONDS":"30","EXTRACTION_MAX_CONCURRENT_OPERATIONS":"1","PROVIDER_OPERATION_CEILING_USD":".05","USER_BUDGET_USD":".50","GLOBAL_BUDGET_USD":"2.00"}
    for key,value in values.items():monkeypatch.setenv(key,value)
    settings=Settings(_env_file=None)
    assert settings.initial_free_analyses==5 and settings.paid_requests_per_minute==12
    assert settings.extraction_max_video_seconds==300 and settings.extraction_max_response_bytes==2097152
    assert settings.provider_operation_ceiling_usd==Decimal(".05") and settings.user_budget_usd==Decimal(".50")
    assert settings.provider_emergency_stop


@pytest.mark.parametrize("key,value",[("USER_BUDGET_USD","-1"),("GLOBAL_BUDGET_USD","NaN"),("PROVIDER_OPERATION_CEILING_USD","Infinity"),("INITIAL_FREE_ANALYSES",-1),("CONCURRENT_ANALYSES_PER_USER",0),("SEMANTIC_ATTEMPTS_PER_SLOT",-1),("EXTRACTION_MAX_VIDEO_SECONDS",-1),("EXTRACTION_MAX_VIDEO_SECONDS",86401),("EXTRACTION_TIMEOUT_SECONDS",121),("CELERY_WORKER_CONCURRENCY",2),("CELERY_QUEUE","bad queue"),("SERVICE_ROLE","typo"),("LLM_TEMPERATURE",float("inf")),("SEMANTIC_MAX_OUTPUT_TOKENS",8193)])
def test_invalid_operational_values_rejected(key,value):
    with pytest.raises(ValidationError):Settings(_env_file=None,**{key:value})


def test_missing_production_auth_and_origins_fail_closed():
    with pytest.raises(ValidationError):Settings(_env_file=None,APPLICATION_ACCESS_MODE="authenticated",ENVIRONMENT="production")
    with pytest.raises(ValidationError):Settings(_env_file=None,ENVIRONMENT="production")
    with pytest.raises(ValidationError):Settings(_env_file=None,ENVIRONMENT="production",DEMO_ACCESS_MODE="local")


@pytest.mark.parametrize("signal",["RENDER_SERVICE_ID","CONTAINER_APP_NAME","CONTAINER_APP_REVISION"])
def test_hosted_environment_cannot_claim_local_bypass(monkeypatch,signal):
    monkeypatch.setenv(signal,"synthetic-host")
    with pytest.raises(ValidationError):Settings(_env_file=None,ENVIRONMENT="local",DEMO_ACCESS_MODE="local")
    assert not hasattr(Settings.model_construct(),"application_access_mode")


def test_active_price_changes_behavior_without_rewriting_archive(monkeypatch):
    from app.llm.pricing_policy import load_pricing_registry, REGISTRY_PATH, resolve_price
    archive=REGISTRY_PATH.read_bytes()
    raw=json.dumps(registry_envelope())
    monkeypatch.setenv("LLM_ACTIVE_PRICING_JSON",raw)
    price=resolve_price(load_pricing_registry(),"gemini","gemini-3.5-flash-lite","standard",date(2026,11,15))
    assert price["input_per_million"]=="1.00" and price["operator_approval"]["change_reference"]=="test-only"
    assert len(price["configuration_sha256"])==64
    historical=resolve_price(load_pricing_registry(REGISTRY_PATH),"gemini","gemini-3.5-flash-lite","standard",date(2026,11,15))
    assert historical["input_per_million"]=="0.30" and REGISTRY_PATH.read_bytes()==archive
    assert resolve_price(load_pricing_registry(),"gemini","gemini-3.6-flash","standard",date(2026,11,15)) is None


@pytest.mark.parametrize("defect",["approval","overlap","source","currency","model","number","missing_version","extra_secret"])
def test_invalid_active_pricing_rejected(defect):
    envelope=registry_envelope();entry=envelope["registry"]["entries"][0]
    if defect=="approval":envelope["approval"]["approved"]=False
    if defect=="overlap":envelope["registry"]["entries"].append(deepcopy(entry))
    if defect=="source":entry["source_url"]="https://untrusted.invalid/prices"
    if defect=="currency":entry["currency"]="EUR"
    if defect=="model":entry["model"]="unknown-model"
    if defect=="number":entry["input_per_million"]=.3
    if defect=="missing_version":del entry["policy_version"]
    if defect=="extra_secret":entry["api_key"]="never-export-this"
    with pytest.raises(ValueError):active_registry(json.dumps(envelope),"llm")


def test_active_extraction_date_and_endpoint_validation():
    from app.extraction.policy import price_for
    envelope=registry_envelope("extraction")
    configured=active_registry(json.dumps(envelope),"extraction")
    assert price_for("metadata","free_prepaid",at=date(2026,11,16),data=configured)["pricing_policy"]=="operator-review-example-1"
    with pytest.raises(HTTPException):price_for("metadata","free_prepaid",at=date(2026,11,17),data=configured)
    envelope["registry"]["entries"][0]["endpoint"]="https://untrusted.invalid"
    with pytest.raises(ValueError):active_registry(json.dumps(envelope),"extraction")


def test_paid_rate_is_global_across_users_and_route_categories():
    from app.core.request_limits import enforce_rate
    buckets={}
    class Redis:
        def eval(self,script,count,key,seconds):
            buckets[key]=buckets.get(key,0)+1
            return buckets[key],60
    connection=Redis();settings=SimpleNamespace(paid_requests_per_minute=2)
    enforce_rate(settings,"first","paid",connection=connection)
    enforce_rate(settings,"second","semantic_submission",connection=connection)
    with pytest.raises(HTTPException) as error:enforce_rate(settings,"third","paid",connection=connection)
    assert error.value.status_code==429 and len(buckets)==1


def create_owner_project(session):
    from app.core.identity import Principal
    from app.core.access import provision,current_principal
    from app.db.repositories.project_repository import ProjectRepository
    owner=Principal(str(uuid4()),str(uuid4()),1)
    provision(session,owner)
    def project():
        handle=current_principal.set(owner)
        try:return ProjectRepository(session).create(project_id=str(uuid4()),content_1_url="one",content_2_url="two",content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
        finally:current_principal.reset(handle)
    return owner,project


def test_changed_grant_applies_only_to_new_users(db_session,monkeypatch):
    from app.core.access import provision
    from app.core.identity import Principal
    from app.db.models.account import UserEntitlement,UsageEvent
    first,_=create_owner_project(db_session)
    monkeypatch.setenv("INITIAL_FREE_ANALYSES","7");get_settings.cache_clear()
    provision(db_session,first)
    second=Principal(str(uuid4()),str(uuid4()),1);provision(db_session,second)
    assert db_session.get(UserEntitlement,first.user_id).granted==5
    assert db_session.get(UserEntitlement,second.user_id).granted==7
    events=db_session.scalars(select(UsageEvent).where(UsageEvent.kind=="lifetime_grant")).all()
    assert sorted(e.details["credits"] for e in events)==[5,7]


def test_changed_concurrency_preserves_project_and_credit_bounds(db_session,monkeypatch):
    from app.services.account_usage import reserve,balance
    monkeypatch.setenv("CONCURRENT_ANALYSES_PER_USER","2");get_settings.cache_clear()
    owner,project=create_owner_project(db_session);a,b,c=project(),project(),project()
    reserve(db_session,owner,a,"request-a");reserve(db_session,owner,b,"request-b")
    for pid,key in [(c,"request-c"),(a,"request-duplicate")]:
        with pytest.raises(HTTPException):reserve(db_session,owner,pid,key)
    assert balance(db_session,owner.user_id)["reserved"]==2


def test_configured_assistant_attempt_limit_and_original_quote(db_session,monkeypatch):
    from app.services.account_usage import reserve,settle
    from app.services.provider_admission import admit
    from app.db.models.account import ProviderOperation
    settings=Settings(_env_file=None,PROVIDER_EMERGENCY_STOP=False,GEMINI_API_KEY="offline-test-only",LLM_CACHE_BILLING_MODE="implicit",USER_BUDGET_USD="1",GLOBAL_BUDGET_USD="2",PROVIDER_OPERATION_CEILING_USD=".05",PROVIDER_INPUT_BYTE_LIMIT=1000,LLM_ESTIMATE_SERVICE_TIER="standard",ASSISTANT_ADMISSIONS_PER_ANALYSIS=1)
    owner,project=create_owner_project(db_session);pid=project();reservation,_=reserve(db_session,owner,pid,"request-one")
    settle(db_session,reservation.id,"completed",completion_mode="metrics_only")
    identifier=admit(db_session,owner,pid,"assistant",settings=settings,rate=False)
    original=deepcopy(db_session.get(ProviderOperation,identifier).provider_details)
    with pytest.raises(HTTPException):admit(db_session,owner,pid,"assistant",settings=settings,rate=False)
    assert original["pricing"]["model"]==settings.llm_model
    monkeypatch.setenv("LLM_ACTIVE_PRICING_JSON",json.dumps(registry_envelope()));get_settings.cache_clear()
    assert db_session.get(ProviderOperation,identifier).provider_details==original


def test_unknown_tier_and_disabled_execution_block_admission():
    from app.services.provider_admission import paid_configuration
    with pytest.raises(HTTPException):paid_configuration(Settings(_env_file=None),"assistant")
    settings=Settings(_env_file=None,PROVIDER_EMERGENCY_STOP=False,GEMINI_API_KEY="offline-test-only",LLM_CACHE_BILLING_MODE="implicit",USER_BUDGET_USD=".5",GLOBAL_BUDGET_USD="2",PROVIDER_OPERATION_CEILING_USD=".05",PROVIDER_INPUT_BYTE_LIMIT=1000,LLM_ESTIMATE_SERVICE_TIER="unsupported")
    with pytest.raises(HTTPException):paid_configuration(settings,"assistant")
    valid=settings.model_copy(update={"llm_estimate_service_tier":"standard"})
    assert paid_configuration(valid,"semantic")==Decimal(".05")
    with pytest.raises(HTTPException):paid_configuration(valid.model_copy(update={"semantic_attempts_per_slot":0}),"semantic")


def test_tracing_drops_private_payloads():
    from app.llm.tracing import TraceSpan
    captured=[]
    TraceSpan(SimpleNamespace(end=lambda **kwargs:captured.append(kwargs))).set_outputs({"answer":"private-conversation"})
    assert captured==[{"outputs":{"payload_redacted":True}}]


def test_configurable_allowance_migration_sql_and_guard():
    from importlib.util import spec_from_file_location,module_from_spec
    from io import StringIO
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from app.db.base import Base
    path=Path(__file__).parents[2]/"alembic/versions/20261115_0014_configurable_allowances.py"
    spec=spec_from_file_location("allowances_revision",path);revision=module_from_spec(spec);spec.loader.exec_module(revision)
    output=StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql",opts={"as_sql":True,"output_buffer":output,"target_metadata":Base.metadata})):
        revision.upgrade()
    sql=output.getvalue()
    assert "granted >= 0" in sql and "consumed + reserved <= granted" in sql
    assert "uq_active_analysis_per_project" in sql and "DROP INDEX uq_active_analysis_per_user" in sql
    assert "UPDATE " not in sql and "DELETE " not in sql
    assert revision.down_revision=="20261114_0013"


def test_provider_pacing_setting_changes_transport_gate():
    from app.extraction.dispatch_limit import enforce_provider_rate
    captured=[]
    fake=SimpleNamespace(set=lambda key,value,**kwargs:captured.append(kwargs) or True)
    settings=SimpleNamespace(supadata_billing_tier="free_prepaid",supadata_request_interval_ms=1500,extraction_timeout_seconds=1,supadata_credit_pool="offline-pool")
    enforce_provider_rate(settings,connection=fake)
    assert captured[0]["px"]==1500
    settings.supadata_request_interval_ms=100
    with pytest.raises(RuntimeError):enforce_provider_rate(settings,connection=fake)


def test_semantic_claim_obeys_updated_attempt_limit(db_session,monkeypatch):
    from contextlib import contextmanager
    from app.db.repositories import semantic_repository as store
    from app.db.repositories.content_item_repository import ContentItemRepository
    owner,project=create_owner_project(db_session);pid=project()
    item=ContentItemRepository(db_session).upsert(project_id=pid,slot="content_1",platform="youtube",url="one",extraction_status="partial",transcript_available=False,transcript_segment_count=0)
    @contextmanager
    def scoped(**kwargs):yield db_session
    monkeypatch.setattr(store,"semantic_session",scoped)
    monkeypatch.setenv("SEMANTIC_ATTEMPTS_PER_SLOT","3");get_settings.cache_clear()
    key="synthetic-key"
    assert store.create_pending(key=key,context={"project_id":pid,"content_id":item.id,"slot":"content_1"},model_id="gemini-3.5-flash-lite",prompt_version="test",schema_version="test")
    for _ in range(3):
        assert store.claim_snapshot(key)
        assert store.transition(key,"running","pending")
    assert not store.claim_snapshot(key)
    monkeypatch.setenv("SEMANTIC_ATTEMPTS_PER_SLOT","1");get_settings.cache_clear()
    assert not store.claim_snapshot(key)


def test_deployed_auth_requires_tls_and_exact_origins():
    common=dict(_env_file=None,ENVIRONMENT="production",APPLICATION_ACCESS_MODE="authenticated",SUPABASE_URL="https://fixture.supabase.co",SUPABASE_JWT_ISSUER="https://fixture.supabase.co/auth/v1",SUPABASE_JWKS_URL="https://fixture.supabase.co/auth/v1/.well-known/jwks.json",DATABASE_URL="postgresql://fixture@db.invalid/db?sslmode=require",REDIS_URL="rediss://redis.invalid:6380/0",CORS_ORIGINS="https://creator.invalid",AUTHENTICATED_REQUESTS_PER_MINUTE=60)
    assert Settings(**common).require_service_configuration()
    for key,value in [("REDIS_URL","redis://redis.invalid/0"),("REDIS_URL","rediss://redis.invalid/0?ssl_cert_reqs=none"),("DATABASE_URL","postgresql://fixture@db.invalid/db"),("CORS_ORIGINS","*"),("CORS_ORIGINS","https://creator.invalid/path")]:
        with pytest.raises(ValidationError):Settings(**{**common,key:value})


def test_preflight_fingerprint_detects_shared_drift_without_secrets():
    from app.core.configuration_preflight import audit
    settings=Settings(_env_file=None,DATABASE_URL="postgresql://private-password@db.invalid/db")
    report=audit(settings)
    assert "private-password" not in json.dumps(report)
    assert audit(settings.model_copy(update={"celery_queue":"other"}))["shared_configuration_sha256"]!=report["shared_configuration_sha256"]
    assert audit(settings,release=True)["status"]=="FAIL"


def test_bundled_registry_numeric_estimate_and_active_history_separation(monkeypatch):
    from app.llm.cost_estimation import estimate_model_cost
    from app.llm.token_usage import parse_token_usage
    from app.llm.pricing_policy import load_pricing_registry,REGISTRY_PATH
    usage=parse_token_usage({"usage_metadata":{"input_tokens":6803,"output_tokens":946,"input_token_details":{"cache_read":0}}})
    archive=load_pricing_registry(REGISTRY_PATH)
    before=estimate_model_cost(usage,provider="gemini",model="gemini-3.5-flash-lite",service_tier="standard",at=date(2026,11,15),caching_mode="implicit",pricing_registry=archive)
    assert Decimal(before["estimated_cost_usd"])==Decimal(".0044059")
    monkeypatch.setenv("LLM_ACTIVE_PRICING_JSON",json.dumps(registry_envelope()));get_settings.cache_clear()
    after=estimate_model_cost(usage,provider="gemini",model="gemini-3.5-flash-lite",service_tier="standard",at=date(2026,11,15),caching_mode="implicit")
    assert after["estimated_cost_usd"]!=before["estimated_cost_usd"]
    assert estimate_model_cost(usage,provider="gemini",model="gemini-3.5-flash-lite",service_tier="standard",at=date(2026,11,15),caching_mode="implicit",pricing_registry=archive)==before


def test_changed_archive_rate_requires_new_policy_version():
    envelope=registry_envelope()
    envelope["registry"]["entries"][0]["policy_version"]="gemini-standard-2026-11-14"
    with pytest.raises(ValueError):active_registry(json.dumps(envelope),"llm")


@pytest.mark.parametrize("changes",[{"gemini_api_key":None},{"llm_cache_billing_mode":"unknown"},{"llm_model":"unapproved-model"}])
def test_incomplete_paid_model_configuration_denied_before_accounting(changes):
    from app.services.provider_admission import paid_configuration
    settings=Settings(_env_file=None,PROVIDER_EMERGENCY_STOP=False,GEMINI_API_KEY="offline-test-only",LLM_CACHE_BILLING_MODE="implicit",USER_BUDGET_USD=".5",GLOBAL_BUDGET_USD="2",PROVIDER_OPERATION_CEILING_USD=".05",PROVIDER_INPUT_BYTE_LIMIT=1000,LLM_ESTIMATE_SERVICE_TIER="standard")
    assert paid_configuration(settings,"semantic")==Decimal(".05")
    with pytest.raises(HTTPException):paid_configuration(settings.model_copy(update=changes),"semantic")


def test_trace_error_export_omits_original_exception_text():
    from app.llm.tracing import OptionalTrace
    captured=[]
    trace=OptionalTrace("fixture",run_type="chain",inputs={},metadata={},settings=Settings(_env_file=None))
    trace._context=SimpleNamespace(__exit__=lambda *args:captured.append(args))
    assert trace.__exit__(ValueError,ValueError("private transcript and credential"),None) is False
    assert captured[0][0] is RuntimeError
    assert "private transcript" not in str(captured[0][1]) and captured[0][2] is None
