"""Signed synthetic JWT -> actual routes/SQL -> mocked bounded extraction.
No production settings, providers, vector store or broker are used.
"""
from contextlib import contextmanager
from datetime import date
from time import time
from uuid import uuid4
import json,sys
import httpx,jwt,pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core.config import Settings
from app.core.identity import JwksVerifier
from app.core.access import current_principal
from app.core.authentication_middleware import AuthenticationMiddleware
from app.db.models.account import AnalysisReservation,ProviderOperation,UserEntitlement,DispatchOutbox
from app.db.repositories import storage_repository as storage
from app.db.repositories.job_repository import JobRepository
from app.api import projects,account,ingestion,insights,chat
from app.services import project_service,metric_source_service,admitted_ingestion,semantic_service
from app.extraction import accounting,bounded_provider,policy
from app.workers import owned_execution,dispatch_outbox,indexing_tasks
from tests.unit.test_bounded_extraction import settings as bounded_settings


@pytest.mark.parametrize("platforms",[("youtube","youtube"),("instagram","facebook"),("facebook","youtube")])
@pytest.mark.parametrize("captions",[True,False])
def test_signed_two_user_analysis_acceptance(db_session,monkeypatch,captions,platforms):
    import app.core.authenticated_access as boundary
    import app.core.authentication_middleware as gate
    import app.insights.insight_service as insight_service
    from app.rag import intelligence_context
    config=vars(bounded_settings()).copy();config.pop("transcript_fallback_language_list")
    config.update(environment="test",supabase_url="https://auth.example",supabase_jwt_issuer="https://auth.example/auth/v1",supabase_jwks_url="https://auth.example/auth/v1/.well-known/jwks.json",supabase_jwt_audience="authenticated",database_url="postgresql+psycopg://fixture:fixture@localhost/creatorlens_test",redis_url="redis://localhost:6379/15",authenticated_requests_per_minute=60,analysis_requests_per_minute=2,llm_model="gemini-3.5-flash-lite")
    settings=Settings(_env_file=None).model_copy(update=config)
    @contextmanager
    def database():yield db_session;db_session.flush()
    # Rebind imported repository helpers to the SAME isolated SQL session, not live URLs.
    for name,module in list(sys.modules.items()):
        if not name.startswith("app.") or module is None:continue
        if hasattr(module,"database_session"):monkeypatch.setattr(module,"database_session",database)
        if hasattr(module,"get_settings"):monkeypatch.setattr(module,"get_settings",lambda:settings)
        for attr,value in list(vars(module).items()):
            if callable(value) and getattr(value,"__module__","")=="app.services.storage_service" and hasattr(storage,attr):
                monkeypatch.setattr(module,attr,getattr(storage,attr))
    monkeypatch.setattr(boundary,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(admitted_ingestion,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(accounting,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(bounded_provider,"enforce_provider_rate",lambda supplied:None)
    monkeypatch.setattr(admitted_ingestion,"paid_configuration",lambda *args:__import__("decimal").Decimal(".01"))
    monkeypatch.setattr(owned_execution,"admit",lambda *args,**kwargs:pytest.fail("Extraction must use its per-request ledger."))
    import app.services.provider_admission as general
    monkeypatch.setattr(general,"paid_configuration",lambda *args:__import__("decimal").Decimal(".01"))
    checked=policy.configuration
    monkeypatch.setattr(accounting,"configuration",lambda supplied:checked(supplied,at=date(2026,11,15)))
    monkeypatch.setattr(bounded_provider,"configuration",lambda supplied:checked(supplied,at=date(2026,11,15)))
    published=[];monkeypatch.setattr(dispatch_outbox,"dispatch",lambda **kwargs:published.append(kwargs) or 1)
    monkeypatch.setattr(semantic_service,"get_semantic_analysis",lambda project,slot:{"status":"unavailable","error_code":"EVIDENCE_UNAVAILABLE","snapshot_id":None,"input_revision":None})
    key=ec.generate_private_key(ec.SECP256R1());jwk=json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()));jwk.update(kid="acceptance",alg="ES256",use="sig")
    monkeypatch.setattr(boundary,"verifier",JwksVerifier(fetch=lambda url:{"keys":[jwk]}))
    ids=[str(uuid4()),str(uuid4())];sessions=[str(uuid4()),str(uuid4())]
    def token(i,expired=False):return jwt.encode(dict(sub=ids[i],session_id=sessions[i],iat=int(time())-60,exp=int(time())-1 if expired else int(time())+300,iss=settings.supabase_jwt_issuer,aud="authenticated",role="authenticated",app_metadata={"provider":"google","providers":["google"]},amr=[{"method":"oauth"}]),key,algorithm="ES256",headers={"kid":"acceptance"})
    headers=[{"Authorization":"Bearer "+token(i)} for i in range(2)]
    app=FastAPI();app.add_middleware(AuthenticationMiddleware)
    for module in (projects,account,ingestion,insights,chat):app.include_router(module.router)
    client=TestClient(app)
    urls=[{"youtube":f"https://www.youtube.com/watch?v=accept_{index}","instagram":f"https://www.instagram.com/reel/accept_{index}/","facebook":f"https://www.facebook.com/reel/{8100+index}/"}[platform] for index,platform in enumerate(platforms)]
    canonical_urls=[policy.input_url(url,platform,settings) for url,platform in zip(urls,platforms)]
    provider_calls=[]
    def handler(request):
        provider_calls.append(request)
        source=request.url.params["url"];second=source==canonical_urls[1];platform=platforms[int(second)]
        if request.url.path.endswith("metadata"):
            body={"platform":platform,"type":"video","url":source,"title":"Synthetic second" if second else "Synthetic first","media":{"duration":30},"stats":{"views":1527222 if second else 34021,"likes":18876 if second else 485,"comments":308 if second else 8}}
            return httpx.Response(200,stream=httpx.ByteStream(json.dumps(body).encode()))
        if not captions:return httpx.Response(404,stream=httpx.ByteStream(b""))
        return httpx.Response(200,stream=httpx.ByteStream(json.dumps({"lang":"en","content":[{"text":"Synthetic topic explanation for this content.","offset":0,"duration":8000}]}).encode()))
    original=httpx.Client
    def provider_client(**kwargs):kwargs["transport"]=httpx.MockTransport(handler);return original(**kwargs)
    monkeypatch.setattr(bounded_provider.httpx,"Client",provider_client)
    for i in range(2):
        response=client.get("/api/account",headers=headers[i]);assert response.status_code==200
        assert "avatar_url" in response.json()
        assert response.json()["usage"]["available"]==5 and response.json()["id"]==ids[i]
        assert client.get("/api/account",headers=headers[i]).json()["usage"]["granted"]==5
    assert client.get("/api/account",headers={"Authorization":"Bearer "+token(0,True)}).status_code==401
    assert client.get("/api/projects").status_code==401
    created=client.post("/api/projects",headers=headers[0],json={"content_1_url":urls[0],"content_2_url":urls[1],"owner_user_id":ids[1]})
    assert created.status_code==201,created.text
    project=created.json()["project_id"]
    path="/api/projects/"+project
    assert client.get("/api/projects",headers=headers[1]).json()["projects"]==[]
    assert client.get(path,headers=headers[1]).status_code==404
    start=client.post(path+"/ingest",headers={**headers[0],"Idempotency-Key":"synthetic-admission"})
    assert start.status_code==202,start.text
    replay=client.post(path+"/ingest",headers={**headers[0],"Idempotency-Key":"synthetic-admission"})
    assert replay.json()["job_id"]==start.json()["job_id"]
    assert client.get("/api/account",headers=headers[0]).json()["usage"]["reserved"]==1
    job_id=start.json()["job_id"]
    observed=[]
    @owned_execution.owned_task("extraction")
    def work(job_id):
        observed.append(current_principal.get().user_id)
        result=project_service.extract_project_videos(project)
        assert len(result.content_items)==2
        # Exercise the real owned index worker and automatic SQL settlement below.
        JobRepository(db_session).get(job_id).status="CHUNKING";db_session.flush()
        return {"status":"CHUNKING"}
    assert work(job_id)["status"]=="CHUNKING"
    from types import SimpleNamespace
    monkeypatch.setattr(indexing_tasks,"index_project",lambda *a,**k:SimpleNamespace(status="indexed",total_chunks=4,message=None))
    assert indexing_tasks.index_project_task.run(job_id)["status"]=="PARTIAL_READY"
    assert indexing_tasks.index_project_task.run(job_id)["status"]=="PARTIAL_READY" and observed==[ids[0]]
    usage_after_index=client.get("/api/account",headers=headers[0]).json()["usage"]
    assert usage_after_index=={"granted":5,"completed":1,"reserved":0,"available":4}
    assert client.get(path+"/usage",headers=headers[0]).json()["analysis_state"]=="completed"
    assert len(provider_calls)==4
    completed=client.post(path+"/complete",headers=headers[0],json={"metrics_only":True})
    assert completed.status_code==200,completed.text
    assert completed.json()["usage"]==usage_after_index  # Older clients remain idempotent.
    for objective,winner in (("reach","content_2"),("engagement","content_1"),("balanced",None),("creative_quality",None)):
        summary=client.get(path+"/insights/summary?objective="+objective,headers=headers[0])
        assert summary.status_code==200,summary.text
        # Historical goal_comparison remains available under its original comparability rules.
        assert summary.json()["goal_comparison"]["winner_slot"]==(winner if platforms==("youtube","youtube") else None)
        current=summary.json()["intelligence"]
        assert current["policy_version"]=="observed-intelligence-1.1.0"
        assert current["decisions"]["reach"]["winner_slot"]=="content_2"
        assert current["decisions"]["like_rate"]["winner_slot"]=="content_1"
        assert current["decisions"]["reach"]["comparison_scope"]==("same_platform" if platforms[0]==platforms[1] else "cross_platform_descriptive")
    from app.rag import chat_service
    monkeypatch.setattr(chat_service,"get_llm",lambda **kwargs:pytest.fail("Deterministic metric answer must not invoke Gemini."))
    stream=client.post(path+"/chat/stream",headers=headers[0],json={"message":"Which video has more views?","objective":"reach"})
    assert stream.status_code==200
    events=[]
    for block in stream.text.strip().split("\n\n"):
        lines=block.splitlines()
        if len(lines)>=2:events.append((lines[0].removeprefix("event: "),json.loads(lines[1].removeprefix("data: "))))
    assert not any(name=="error" for name,data in events),stream.text
    structured=[data for name,data in events if name=="structured_answer"]
    assert len(structured)==1 and structured[0]["answer"]["winner"]=="content_2"
    assert sum(name=="done" for name,data in events)==1
    assert not db_session.scalar(select(ProviderOperation.id).where(ProviderOperation.project_id==project,ProviderOperation.kind=="assistant"))
    usage=client.get(path+"/usage",headers=headers[0]).json()
    assert len(usage["extraction_operations"])==4
    assert all(op["actual_billed_cost_usd"] is None for op in usage["extraction_operations"])
    for suffix in ("","/usage","/transcripts?slot=content_1","/insights/summary","/semantic/content_1","/chat/sessions/stolen"):
        assert client.get(path+suffix,headers=headers[1]).status_code==404
    assert client.post(path+"/ingest",headers={**headers[1],"Idempotency-Key":"forged-admission"}).status_code==404
    assert client.get("/api/account",headers=headers[1]).json()["usage"]["available"]==5
    assert len(provider_calls)==4 and db_session.get(UserEntitlement,ids[0]).consumed==1
    assert client.post("/api/account/logout",headers=headers[0]).status_code==200
    assert client.get(path,headers=headers[0]).status_code==403
