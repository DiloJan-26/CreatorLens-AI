"""No providers: deny requests before project storage, queue or inference handlers."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core import demo_access
from app.core.config import Settings


async def handle_lifespan(scope, receive, send):
    if scope['type'] != 'lifespan':
        pytest.fail('Restricted HTTP request reached application data or provider code')
    while True:
        message = await receive()
        if message['type'] == 'lifespan.startup':
            await send({'type': 'lifespan.startup.complete'})
        elif message['type'] == 'lifespan.shutdown':
            await send({'type': 'lifespan.shutdown.complete'})
            return


@pytest.mark.parametrize('path,method', [
    ('/api/projects', 'GET'), ('/api/projects', 'POST'),
    ('/api/projects/private-project', 'GET'), ('/api/projects/private-project', 'DELETE'),
    ('/api/projects/private-project/transcript', 'GET'), ('/api/projects/private-project/chunks', 'GET'),
    ('/api/projects/private-project/semantic/content_1', 'POST'),
    ('/api/projects/private-project/chat/stream', 'POST'),
    ('/api/projects/private-project/sessions/private-session', 'GET'),
    ('/api/metrics/cost', 'GET'), ('/api/evaluations/runs', 'GET'),
    ('/health/llm/test', 'POST'), ('/health/embeddings', 'GET'),
    ('/docs', 'GET'), ('/openapi.json', 'GET'),
])
def test_restricted_demo_default_boundary_never_dispatches(monkeypatch, path, method):
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='test'))
    async def forbidden(scope, receive, send):
        await handle_lifespan(scope, receive, send)
    with TestClient(demo_access.DemoAccessMiddleware(forbidden)) as client:
        response = client.request(method, path)
    assert response.status_code == 403
    assert 'private-project' not in response.text


@pytest.mark.parametrize('environment,mode,client_host,expected', [
    ('production', 'local', '127.0.0.1', 403),
    ('dev-staging', 'local', '127.0.0.1', 403),
    ('test', 'local', '203.0.113.5', 403),
    ('test', 'local', '127.0.0.1', 200),
    ('test', 'local', '::1', 200),
])
def test_restricted_demo_no_proxy_header_or_environment_bypass(monkeypatch, environment, mode, client_host, expected):
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT=environment, DEMO_ACCESS_MODE=mode))
    app = FastAPI()
    @app.get('/private')
    def private(): return {'fixture': 'synthetic'}
    app.add_middleware(demo_access.DemoAccessMiddleware)
    with TestClient(app, client=(client_host, 50000)) as client:
        result = client.get('/private', headers={'X-Forwarded-For': '127.0.0.1', 'Host': 'localhost'})
    assert result.status_code == expected


@pytest.mark.parametrize('path', ['/health/llm/test', '/health/llm/stream-test',
    '/api/projects/example/ingest', '/api/projects/example/extract',
    '/api/projects/example/index', '/api/projects/example/semantic/content_1'])
def test_restricted_demo_local_provider_actions_remain_disabled(monkeypatch, path):
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='test', DEMO_ACCESS_MODE='local'))
    async def forbidden(scope, receive, send): await handle_lifespan(scope, receive, send)
    with TestClient(demo_access.DemoAccessMiddleware(forbidden)) as client:
        assert client.post(path).status_code == 403


def test_restricted_demo_public_health_is_sanitized_without_handler_or_settings(monkeypatch):
    def forbidden(): pytest.fail('Public health accessed settings')
    monkeypatch.setattr(demo_access, 'get_settings', forbidden)
    async def handler(scope, receive, send): await handle_lifespan(scope, receive, send)
    with TestClient(demo_access.DemoAccessMiddleware(handler)) as client:
        assert client.get('/health').json() == {'status': 'ok', 'service': 'creatorlens-api'}


def test_restricted_demo_actual_app_boundary_covers_all_routes(monkeypatch):
    from app.main import app
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='test'))
    # No context manager: do not enter the actual DB-initializing app lifespan.
    client = TestClient(app)
    try:
        assert client.get('/api/projects').status_code == 403
        assert client.get('/api/metrics/cost').status_code == 403
        assert client.get('/docs').status_code == 403
        response = client.get('/api/projects', headers={'Origin': 'http://localhost:3000'})
        assert response.status_code == 403
        assert response.headers['access-control-allow-origin'] == 'http://localhost:3000'
        assert 'disabled' in response.json()['detail']
    finally: client.close()


def test_restricted_demo_sdk_disabled_before_client_creation(monkeypatch):
    from app.services import llm_service
    monkeypatch.setattr(llm_service, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='test', GEMINI_API_KEY='offline-test-value'))
    monkeypatch.setattr(llm_service, '_get_gemini_llm', lambda **_: pytest.fail('SDK construction is forbidden'))
    with pytest.raises(llm_service.LLMConfigurationError, match='disabled'):
        llm_service.get_llm()


def test_restricted_demo_nonlocal_worker_requeues_without_work(monkeypatch):
    from celery.exceptions import Reject
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='production', DEMO_ACCESS_MODE='local', DEMO_ALLOW_PROVIDER_CALLS=True))
    with pytest.raises(Reject) as result: demo_access.require_local_worker()
    assert result.value.requeue is True


@pytest.mark.parametrize('headers', [
    {'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'}, {'Origin': 'null'},
    {'Host': 'attacker.example', 'X-Forwarded-Host': 'localhost'},
])
def test_restricted_demo_rejects_rebinding_and_cross_site_requests(monkeypatch, headers):
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='test', DEMO_ACCESS_MODE='local'))
    with TestClient(demo_access.DemoAccessMiddleware(handle_lifespan), client=('127.0.0.1', 50000)) as client:
        assert client.get('/api/projects', headers=headers).status_code == 403


@pytest.mark.parametrize('module,name', [
    ('app.workers.ingestion_tasks', 'ingest_project_task'),
    ('app.workers.indexing_tasks', 'index_project_task'),
    ('app.workers.semantic_tasks', 'extract_semantic_features'),
])
def test_restricted_demo_actual_worker_tasks_reject_before_storage(monkeypatch, module, name):
    from importlib import import_module
    from celery.exceptions import Reject
    monkeypatch.setattr(demo_access, 'get_settings', lambda: Settings(_env_file=None, ENVIRONMENT='production'))
    with pytest.raises(Reject) as result:
        getattr(import_module(module), name).run('not-a-real-job')
    assert result.value.requeue is True
