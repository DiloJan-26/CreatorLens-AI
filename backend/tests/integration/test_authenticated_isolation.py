from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.core.identity import Principal
from app.core.access import provision,current_principal
from app.core.demo_access import DemoAccessMiddleware
from app.db.repositories.project_repository import ProjectRepository
from app.db.models.account import AppUser


@pytest.fixture
def boundary(db_session,monkeypatch):
    import app.core.demo_access as gate
    import app.core.authenticated_access as access
    a=Principal(str(uuid4()),str(uuid4()),1);b=Principal(str(uuid4()),str(uuid4()),1)
    provision(db_session,a);provision(db_session,b)
    token=current_principal.set(b)
    try:p=ProjectRepository(db_session).create(project_id=str(uuid4()),content_1_url="one",content_2_url="two",content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
    finally:current_principal.reset(token)
    @contextmanager
    def database():
        yield db_session
        db_session.flush()
    settings=SimpleNamespace(application_access_mode="authenticated",environment="test")
    monkeypatch.setattr(gate,"get_settings",lambda:settings)
    monkeypatch.setattr(access,"database_session",database)
    monkeypatch.setattr(access,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(access.verifier,"verify",lambda token,settings:a if token=="user-a" else b)
    app=FastAPI();app.add_middleware(DemoAccessMiddleware)
    @app.api_route("/{path:path}",methods=["GET","POST","DELETE"])
    def reached(path):return {"reached":True}
    return TestClient(app),p,a,b,db_session


@pytest.mark.parametrize("suffix",["","/transcripts","/chunks","/retrieve","/metadata-availability","/status","/insights/summary","/semantic/content_1","/chat/sessions/stolen","/metrics/sources/stolen","/retrieval-runs","/usage","/complete","/ingest"])
def test_all_project_paths_deny_other_user_before_service(boundary,suffix):
    client,p,*_=boundary
    response=client.get("/api/projects/"+p+suffix,headers={"Authorization":"Bearer user-a"})
    assert response.status_code==404


def test_anonymous_global_analytics_diagnostics_and_ownerless(boundary):
    client,p,a,b,session=boundary
    assert client.get("/api/projects").status_code==401
    for path in ["/api/metrics/cost","/api/evaluations/runs","/api/evaluations/runs/private","/health/llm","/openapi.json"]:
        assert client.get(path,headers={"Authorization":"Bearer user-a"}).status_code==403
    assert client.get("/api/metrics/cost?project_id="+p,headers={"Authorization":"Bearer user-a"}).status_code==404
    assert client.get("/api/projects/"+p,headers={"Authorization":"Bearer user-b"}).status_code==200
    session.get(AppUser,b.user_id).role="admin";session.flush()
    assert client.get("/api/evaluations/runs",headers={"Authorization":"Bearer user-b"}).status_code==200
    assert client.post("/health/llm/test",headers={"Authorization":"Bearer user-b"}).status_code==403
    assert client.get("/health").json()=={"status":"ok","service":"creatorlens-api"}
