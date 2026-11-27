"""Real middleware and routers, fake verified Google sessions, isolated SQL/Redis."""
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.core.identity import Principal
from app.core.access import provision,current_principal
from app.core.authentication_middleware import AuthenticationMiddleware
from app.db.repositories.project_repository import ProjectRepository
from app.db.repositories.evaluation_repository import EvaluationRepository
from app.db.models.account import AppUser
from tests.engineering_fixtures import FakeEngineeringRedis
from tests.unit.test_engineering_access import KEY

@pytest.fixture
def boundary(db_session,monkeypatch):
    from app.core import authentication_middleware,authenticated_access,engineering_access,config
    from app.api import engineering,evaluations,metrics,account
    from app.services import llm_observability_service
    settings=Settings(_env_file=None,ENVIRONMENT='test',ENGINEERING_ACCESS_KEY=KEY,REDIS_URL='redis://localhost:6379',
        SUPABASE_URL='https://auth.example',SUPABASE_JWT_ISSUER='https://auth.example/auth/v1',SUPABASE_JWKS_URL='https://auth.example/auth/v1/.well-known/jwks.json')
    a=Principal(str(uuid4()),str(uuid4()),1);b=Principal(str(uuid4()),str(uuid4()),1)
    principals={'a':a,'b':b,'a-new-session':replace(a,session_id=str(uuid4()))}
    for p in (a,b):provision(db_session,p)
    token=current_principal.set(b)
    try:project=ProjectRepository(db_session).create(project_id=str(uuid4()),content_1_url='one',content_2_url='two',content_1_platform='youtube',content_2_platform='youtube',status='created')['project_id']
    finally:current_principal.reset(token)
    @contextmanager
    def database():yield db_session;db_session.flush()
    for module in (authenticated_access,evaluations,account,llm_observability_service):monkeypatch.setattr(module,'database_session',database)
    for module in (authentication_middleware,engineering,account,config):monkeypatch.setattr(module,'get_settings',lambda:settings)
    monkeypatch.setattr(authenticated_access,'enforce_rate',lambda *a:None)
    monkeypatch.setattr(authenticated_access.verifier,'verify',lambda token,settings:principals[token])
    redis=FakeEngineeringRedis();monkeypatch.setattr(engineering_access,'client',lambda _:redis)
    monkeypatch.setattr(llm_observability_service,'is_database_configured',lambda:True)
    monkeypatch.setattr(evaluations,'run_regression',lambda *a,**kw:pytest.fail('Read-only Engineering invoked an evaluation'))
    app=FastAPI();app.add_middleware(AuthenticationMiddleware)
    for router in (engineering.router,evaluations.router,metrics.cost_router,account.router):app.include_router(router)
    @app.get('/api/projects/{project_id}')
    def project_read(project_id:str):return {'id':project_id}
    with TestClient(app) as client:yield client,settings,redis,a,b,project,db_session


def headers(user='a'):return {'Authorization':'Bearer '+user}
def unlock(client,user='a'):return client.post('/api/engineering/unlock',headers=headers(user),json={'access_key':KEY})

@pytest.mark.parametrize('path,method',[('/api/engineering/access','GET'),('/api/engineering/unlock','POST'),('/api/engineering/lock','POST'),('/api/evaluations/datasets','GET'),('/api/metrics/cost','GET')])
def test_engineering_always_requires_google_identity(boundary,path,method):
    client,*_=boundary
    assert client.request(method,path).status_code==401

@pytest.mark.parametrize('path',['/api/evaluations/datasets','/api/evaluations/runs','/api/evaluations/runs/private','/api/metrics/cost'])
def test_direct_reads_are_denied_before_unlock(boundary,path):
    client,*_=boundary
    r=client.get(path,headers=headers());assert r.status_code==403
    assert r.headers['Cache-Control']=='private, no-store'


def test_one_unlock_opens_both_sections_without_promoting_account(boundary):
    client,settings,redis,a,b,project,session=boundary
    assert unlock(client).json()['expires_in']==1800
    assert client.get('/api/evaluations/datasets',headers=headers()).status_code==200
    assert client.get('/api/evaluations/runs',headers=headers()).status_code==200
    result=client.get('/api/metrics/cost',headers=headers())
    assert result.status_code==200 and result.json()['runs']==[]
    assert session.get(AppUser,a.user_id).role=='user'
    assert client.get('/api/engineering/access',headers=headers()) .json()['unlocked']
    assert not client.get('/api/engineering/access',headers=headers('b')).json()['unlocked']
    assert not client.get('/api/engineering/access',headers=headers('a-new-session')).json()['unlocked']


def test_lock_and_expiry_revoke_both_pages_server_side(boundary):
    client,settings,redis,*_=boundary
    unlock(client);assert client.post('/api/engineering/lock',headers=headers()).status_code==200
    for path in ('/api/evaluations/runs','/api/metrics/cost'):assert client.get(path,headers=headers()).status_code==403
    assert client.get('/api/account',headers=headers()).status_code==200  # Locking Engineering keeps Google sign-in active.
    unlock(client);redis.now+=1800
    for path in ('/api/evaluations/runs','/api/metrics/cost'):assert client.get(path,headers=headers()).status_code==403


def test_admin_also_needs_key_and_key_does_not_allow_writes_or_other_projects(boundary):
    client,settings,redis,a,b,project,session=boundary
    session.get(AppUser,a.user_id).role='admin';session.flush()
    assert client.get('/api/evaluations/runs',headers=headers()).status_code==403
    session.get(AppUser,a.user_id).role='user';session.flush()
    unlock(client)
    assert client.post('/api/evaluations/runs',headers=headers(),json={}).status_code==403
    assert client.post('/health/llm/test',headers=headers(),json={}).status_code==403
    assert client.get('/api/projects/'+project,headers=headers()).status_code==404
    assert client.get('/api/metrics/cost?project_id='+project,headers=headers()).status_code==404
    assert client.get('/api/projects/'+project,headers=headers('b')).status_code==200


def test_logout_revokes_unlock_and_google_session(boundary):
    client,*_=boundary;unlock(client)
    assert client.post('/api/account/logout',headers=headers()).status_code==200
    assert client.get('/api/engineering/access',headers=headers()).status_code==403
    assert client.get('/api/evaluations/runs',headers=headers()).status_code==403


def test_rotation_and_redis_outage_fail_closed(boundary):
    from pydantic import SecretStr
    client,settings,redis,*_=boundary;unlock(client)
    settings.engineering_access_key=SecretStr('new-engineering-secret-0123456789abcdef')
    assert client.get('/api/evaluations/runs',headers=headers()).status_code==403
    redis.failed=True
    assert client.get('/api/engineering/access',headers=headers()).status_code==503
    assert client.get('/api/metrics/cost',headers=headers()).status_code==503


def test_bounded_requests_never_echo_access_key(boundary):
    client,*_=boundary
    for body in ('not-json','{"access_key":2}','{"access_key":"'+KEY+'","extra":true}'):
        r=client.post('/api/engineering/unlock',headers={**headers(),'Content-Type':'application/json'},content=body)
        assert r.status_code==400 and KEY not in r.text
    r=client.post('/api/engineering/unlock',headers=headers(),content='x'*2049)
    assert r.status_code==413
    assert KEY not in str(client.get('/api/engineering/access',headers=headers()).json())


def test_only_bundled_benchmark_histories_are_exposed(boundary):
    client,settings,redis,a,b,project,session=boundary;repository=EvaluationRepository(session)
    rows=[]
    for name in ('creatorlens_core_v1','private-project-evaluation'):
        dataset=repository.create_dataset(name=name,version='1.0.0',source_path='offline-fixture')
        rows.append(repository.start_run(dataset_id=dataset.id,evaluator='fixture',total_cases=0))
    unlock(client)
    assert [r['id'] for r in client.get('/api/evaluations/runs',headers=headers()).json()]==[rows[0].id]
    assert client.get('/api/evaluations/runs/'+rows[0].id,headers=headers()).status_code==200
    assert client.get('/api/evaluations/runs/'+rows[1].id,headers=headers()).status_code==404
    assert repository.get_run(rows[1].id) is not None


def test_global_aggregate_path_never_queries_private_run_details(boundary,monkeypatch):
    from app.db.repositories.llm_run_repository import LlmRunRepository
    client,*_=boundary;unlock(client)
    monkeypatch.setattr(LlmRunRepository,'list_recent',lambda *a,**kw:pytest.fail('Global summary queried individual runs'))
    r=client.get('/api/metrics/cost',headers=headers())
    assert r.status_code==200 and r.json()['project_id'] is None and r.json()['runs']==[]
