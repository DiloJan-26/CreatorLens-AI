"""Permanent request and worker boundary; every fixture is offline."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core import authentication_middleware as gate
from app.core.config import Settings


async def forbidden(scope,receive,send):
    if scope["type"]!="lifespan":pytest.fail("Unauthorized request reached private application code")
    while True:
        message=await receive()
        if message["type"]=="lifespan.startup":await send({"type":"lifespan.startup.complete"})
        elif message["type"]=="lifespan.shutdown":
            await send({"type":"lifespan.shutdown.complete"});return


@pytest.mark.parametrize("path,method",[("/api/projects","GET"),("/api/projects","POST"),("/api/projects/private-project","GET"),("/api/projects/private-project","DELETE"),("/api/projects/private-project/transcript","GET"),("/api/projects/private-project/chunks","GET"),("/api/projects/private-project/semantic/content_1","POST"),("/api/projects/private-project/chat/stream","POST"),("/api/projects/private-project/sessions/private-session","GET"),("/api/metrics/cost","GET"),("/api/evaluations/runs","GET"),("/health/llm/test","POST"),("/health/embeddings","GET"),("/docs","GET"),("/openapi.json","GET"),("/api/providers/status","GET"),("/api/demo/capabilities","GET"),("/health/llm/stream-test","POST"),("/api/projects/private-project/ingest","POST"),("/api/projects/private-project/extract","POST"),("/api/projects/private-project/index","POST")])
def test_all_private_routes_require_identity(monkeypatch,path,method):
    monkeypatch.setattr(gate,"get_settings",lambda:Settings(_env_file=None,ENVIRONMENT="test"))
    with TestClient(gate.AuthenticationMiddleware(forbidden)) as client:
        response=client.request(method,path)
        assert response.status_code==401
        assert "private-project" not in response.text


@pytest.mark.parametrize("environment,client_host",[("local","127.0.0.1"),("test","::1"),("test","203.0.113.5")])
def test_retired_modes_and_proxy_headers_cannot_bypass_identity(monkeypatch,environment,client_host):
    settings=Settings(_env_file=None,ENVIRONMENT=environment,APPLICATION_ACCESS_MODE="disabled",DEMO_ACCESS_MODE="local",DEMO_ALLOW_PROVIDER_CALLS=True)
    monkeypatch.setattr(gate,"get_settings",lambda:settings)
    with TestClient(gate.AuthenticationMiddleware(forbidden),client=(client_host,50000)) as client:
        assert client.get("/api/projects",headers={"Host":"localhost","X-Forwarded-For":"127.0.0.1","Origin":"http://localhost:3000"}).status_code==401


def test_process_health_never_reads_private_settings(monkeypatch):
    monkeypatch.setattr(gate,"get_settings",lambda:pytest.fail("Health accessed configuration"))
    with TestClient(gate.AuthenticationMiddleware(forbidden)) as client:
        assert client.get("/health").json()=={"status":"ok","service":"creatorlens-api"}


def test_missing_verification_config_fails_closed(monkeypatch):
    monkeypatch.setattr(gate,"get_settings",lambda:Settings(_env_file=None,ENVIRONMENT="test"))
    with TestClient(gate.AuthenticationMiddleware(forbidden)) as client:
        assert client.get("/api/projects",headers={"Authorization":"Bearer synthetic"}).status_code==503


def test_actual_application_routes_are_permanently_gated(monkeypatch):
    from app.main import app
    monkeypatch.setattr(gate,"get_settings",lambda:Settings(_env_file=None,ENVIRONMENT="test"))
    client=TestClient(app)
    try:
        for path in ("/api/projects","/api/metrics/cost","/api/providers/status","/api/demo/capabilities","/docs"):
            assert client.get(path).status_code==401
    finally:client.close()


@pytest.mark.parametrize("headers",[{"Host":"attacker.example"},{"Origin":"https://attacker.example"},{"Origin":"null"},{"Host":"localhost","X-Forwarded-Host":"localhost"}])
def test_no_origin_or_host_header_substitutes_for_identity(monkeypatch,headers):
    monkeypatch.setattr(gate,"get_settings",lambda:Settings(_env_file=None,ENVIRONMENT="test"))
    with TestClient(gate.AuthenticationMiddleware(forbidden),client=("127.0.0.1",50000)) as client:
        assert client.get("/api/projects",headers=headers).status_code==401


@pytest.mark.parametrize("module,name",[("app.workers.ingestion_tasks","ingest_project_task"),("app.workers.indexing_tasks","index_project_task"),("app.workers.semantic_tasks","extract_semantic_features")])
def test_unknown_worker_tasks_never_execute_provider_code(monkeypatch,module,name):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from importlib import import_module
    from celery.exceptions import Reject
    import app.workers.owned_execution as execution
    @contextmanager
    def empty_database():yield SimpleNamespace(get=lambda *args:None)
    monkeypatch.setattr(execution,"database_session",empty_database)
    with pytest.raises(Reject) as error:getattr(import_module(module),name).run("unknown-job")
    assert not error.value.requeue


def test_emergency_stop_denies_sdk_before_client_creation(monkeypatch):
    from app.services import llm_service
    from app.services.provider_admission import operation_scope
    monkeypatch.setattr(llm_service,"get_settings",lambda:Settings(_env_file=None,GEMINI_API_KEY="offline-only",PROVIDER_EMERGENCY_STOP=True))
    monkeypatch.setattr(llm_service,"_get_gemini_llm",lambda **kwargs:pytest.fail("SDK construction under emergency stop"))
    with operation_scope("synthetic-admission"),pytest.raises(llm_service.LLMConfigurationError):llm_service.get_llm()


def test_worker_role_does_not_disable_http_authentication(monkeypatch):
    settings=Settings(_env_file=None,ENVIRONMENT="production",SERVICE_ROLE="worker",DATABASE_URL="postgresql://fixture@db.invalid/db?sslmode=require",REDIS_URL="rediss://redis.invalid:6380/0")
    monkeypatch.setattr(gate,"get_settings",lambda:settings)
    with TestClient(gate.AuthenticationMiddleware(forbidden)) as client:
        assert client.get("/api/projects").status_code==401
        assert client.get("/api/projects",headers={"Authorization":"Bearer synthetic"}).status_code==503
