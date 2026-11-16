"""Production invariants and minimal profiles, using no external services."""
from decimal import Decimal
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.core.config import Settings
from app.core.access import current_principal
from app.core.identity import Principal
from app.services.provider_admission import paid_configuration,operation_scope


def test_approved_product_defaults_need_no_environment_overrides():
    s=Settings(_env_file=None)
    assert (s.initial_free_analyses,s.concurrent_analyses_per_user,s.assistant_admissions_per_analysis,s.semantic_attempts_per_slot)==(5,1,3,2)
    assert (s.authenticated_requests_per_minute,s.analysis_requests_per_minute,s.paid_requests_per_minute)==(120,2,12)
    assert (s.extraction_max_video_seconds,s.extraction_max_url_bytes,s.extraction_max_response_bytes,s.extraction_timeout_seconds,s.extraction_max_concurrent_operations)==(300,2048,2097152,30,1)
    assert (s.provider_operation_ceiling_usd,s.user_budget_usd,s.global_budget_usd)==(Decimal(".05"),Decimal(".50"),Decimal("2"))
    assert s.supadata_credit_pool_cap==100 and s.supadata_credit_limit==0 and s.provider_emergency_stop


@pytest.mark.parametrize("obsolete",[{"PAID_OPERATIONS_ENABLED":True},{"EXTRACTION_ENABLED":True},{"APPLICATION_ACCESS_MODE":"disabled","DEMO_ACCESS_MODE":"local","DEMO_ALLOW_PROVIDER_CALLS":True}])
def test_retired_switches_cannot_release_emergency_stop(obsolete):
    s=Settings(_env_file=None,**obsolete)
    assert s.provider_emergency_stop
    with pytest.raises(HTTPException):paid_configuration(s,"assistant")


@pytest.mark.parametrize("user,operation",[(False,True),(True,False),(False,False)])
def test_releasing_stop_does_not_skip_identity_or_admission(monkeypatch,user,operation):
    from app.services import llm_service
    settings=Settings(_env_file=None,PROVIDER_EMERGENCY_STOP=False,GEMINI_API_KEY="offline-only")
    monkeypatch.setattr(llm_service,"get_settings",lambda:settings)
    monkeypatch.setattr(llm_service,"_get_gemini_llm",lambda **kwargs:pytest.fail("Unadmitted SDK construction"))
    token=current_principal.set(Principal(str(uuid4()),str(uuid4()),1) if user else None)
    try:
        with operation_scope("synthetic" if operation else None),pytest.raises(llm_service.LLMConfigurationError):llm_service.get_llm()
    finally:current_principal.reset(token)


@pytest.mark.parametrize("platform",["instagram","facebook"])
def test_stop_release_never_enables_unapproved_extraction(monkeypatch,platform):
    from app.extraction import bounded_provider
    from app.extraction.policy import ExtractionSafetyError
    monkeypatch.setattr(bounded_provider,"request",lambda *args:pytest.fail("Unsupported provider request"))
    with pytest.raises(ExtractionSafetyError,match="YouTube"):bounded_provider.extract("project","content_1",platform,"https://example.invalid")


def test_minimal_api_and_worker_profiles_share_actual_execution_policy():
    from app.core.configuration_preflight import audit
    common=dict(_env_file=None,ENVIRONMENT="production",DATABASE_URL="postgresql://fixture@db.invalid/db?sslmode=require",REDIS_URL="rediss://redis.invalid:6380/0",QDRANT_URL="https://qdrant.invalid",QDRANT_API_KEY="offline-only")
    api=Settings(**common,SUPABASE_URL="https://fixture.supabase.co",SUPABASE_JWT_ISSUER="https://fixture.supabase.co/auth/v1",SUPABASE_JWKS_URL="https://fixture.supabase.co/auth/v1/.well-known/jwks.json",CORS_ORIGINS="https://creator.invalid")
    worker=Settings(**common,SERVICE_ROLE="worker")
    assert audit(api,release=True)["status"]==audit(worker,release=True)["status"]=="PASS"
    assert audit(api)["shared_configuration_sha256"]==audit(worker)["shared_configuration_sha256"]
