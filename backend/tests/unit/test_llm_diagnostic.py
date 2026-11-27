"""Bounded diagnostic deadline, status classification and validated operational settings."""
import asyncio
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.services.llm_diagnostic_service import provider_failure


@pytest.mark.parametrize("code,reason",[(429,"provider_limit"),("RESOURCE_EXHAUSTED","provider_limit"),(403,"provider_access"),(404,"model_unavailable"),(500,"provider_error")])
def test_failure_codes_are_structured_and_sanitized(code,reason):
    error=RuntimeError("secret must not be exposed");error.status_code=code
    assert provider_failure(error)[0]==reason
    assert "secret" not in provider_failure(error)[1]


@pytest.mark.parametrize("key,value",[("DIAGNOSTIC_ATTEMPTS_PER_ANALYSIS",-1),("DIAGNOSTIC_ATTEMPTS_PER_ANALYSIS",11),("DIAGNOSTIC_COOLDOWN_SECONDS",0),("DIAGNOSTIC_COOLDOWN_SECONDS",59)])
def test_diagnostic_limits_validate(key,value):
    with pytest.raises(ValidationError):Settings(_env_file=None,**{key:value})


def test_diagnostic_deadline_records_failed_invocation_without_retry(monkeypatch):
    from app.services import llm_observability_service as telemetry
    from app.services.llm_service import _tracked_diagnostic_invoke
    calls=[];failed=[];costs=[]
    monkeypatch.setattr(telemetry,"start_llm_run",lambda **kw:"offline-run")
    monkeypatch.setattr(telemetry,"fail_llm_run",lambda *a,**kw:failed.append(kw))
    monkeypatch.setattr(telemetry,"record_cost_event",lambda **kw:costs.append(kw))
    monkeypatch.setattr(telemetry,"annotate_operation",lambda *a,**kw:None)
    class Slow:
        async def ainvoke(self,prompt):calls.append(prompt);await asyncio.sleep(1)
    with pytest.raises(TimeoutError):asyncio.run(_tracked_diagnostic_invoke(Slow(),"Reply with OK.","fixture",project_id="owned-project",timeout=.001))
    assert calls==["Reply with OK."] and failed[0]["provider_invocation_count"]==1
    assert costs[0]["project_id"]=="owned-project" and costs[0]["provider_invocation_count"]==1


def test_wrapped_quota_and_network_errors_are_not_reported_as_model_outage():
    cause=RuntimeError("private provider payload");cause.code=429
    wrapper=RuntimeError("private wrapper");wrapper.__cause__=cause
    assert provider_failure(wrapper)[0]=="provider_limit"
    assert provider_failure(ConnectionError("private host"))[0]=="network_error"
