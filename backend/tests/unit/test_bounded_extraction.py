"""Offline provider safety assertions; no real credentials, transports or accounts."""
from contextlib import contextmanager
from datetime import date, datetime, UTC, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import json
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.extraction import policy, accounting, bounded_provider as provider
from app.core.access import provision, current_principal
from app.core.identity import Principal
from app.db.models.account import AppUser, ProviderOperation, BudgetAccount, DispatchOutbox
from app.db.repositories.project_repository import ProjectRepository
from app.db.repositories.job_repository import JobRepository
from app.services.account_usage import reserve, settle, balance

URL = "https://www.youtube.com/watch?v=bounded_one"
OTHER = "https://www.youtube.com/watch?v=bounded_two"


def settings(**changes):
    values=dict(application_access_mode="authenticated", extraction_enabled=True,
        paid_operations_enabled=True, extraction_max_concurrent_operations=2,
        extraction_max_video_seconds=300, extraction_max_url_bytes=2048,
        extraction_max_response_bytes=16384, extraction_timeout_seconds=5,
        supadata_billing_tier="pro_monthly_prepaid", supadata_prepaid_verified=True,
        supadata_auto_recharge_disabled=True, supadata_api_key="offline-fixture-key",
        supadata_credit_pool="offline-fixture-pool", supadata_credit_limit=100,
        supadata_transcript_mode="native", provider_operation_ceiling_usd=".01",
        user_budget_usd="1", global_budget_usd="10", paid_requests_per_minute=1,
        transcript_language="en", transcript_fallback_language_list=lambda:["en"])
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture
def owned(db_session, monkeypatch):
    principal=Principal(str(uuid4()), str(uuid4()), 1)
    provision(db_session, principal)
    handle=current_principal.set(principal)
    project=ProjectRepository(db_session).create(project_id=str(uuid4()),content_1_url=URL,
        content_2_url=OTHER,content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
    reservation,_=reserve(db_session,principal,project,"bounded-request-1")
    job=JobRepository(db_session).create(project)
    reservation.job_id=job.id
    db_session.add(DispatchOutbox(id=job.id,reservation_id=reservation.id,task_name="creatorlens.ingest_project",argument=job.id,state="claimed"))
    db_session.flush()
    s=settings()
    original_configuration=policy.configuration
    monkeypatch.setattr(accounting,"configuration",lambda supplied:original_configuration(supplied,at=date(2026,11,14)))
    monkeypatch.setattr(provider,"configuration",lambda supplied:original_configuration(supplied,at=date(2026,11,14)))
    import app.services.provider_admission as general_admission
    monkeypatch.setattr(general_admission,"paid_configuration",lambda supplied,kind:Decimal(".01"))
    monkeypatch.setattr(accounting,"get_settings",lambda:s)
    monkeypatch.setattr(accounting,"enforce_rate",lambda *args:None)
    monkeypatch.setattr(provider,"get_settings",lambda:s)
    monkeypatch.setattr(provider,"enforce_provider_rate",lambda supplied:None)
    @contextmanager
    def database():
        yield db_session
        db_session.flush()
    monkeypatch.setattr(accounting,"database_session",database)
    yield principal, project, reservation, job, s
    current_principal.reset(handle)


def admit(db_session, owned, operation="metadata", slot="content_1"):
    principal,project,_,_,s=owned
    return accounting.admit(db_session,principal,project,slot,URL if slot=="content_1" else OTHER,"youtube",operation,settings=s,rate=False)


def preflight(db_session, owned, slot="content_1"):
    identifier=admit(db_session,owned,slot=slot)
    accounting.claim(db_session,identifier,owned[0])
    accounting.finish(db_session,identifier,"completed",verified_duration=30,response_status=200)
    db_session.flush()
    return identifier


@pytest.mark.parametrize("tier,cost,credits",[("free_prepaid","0",100),("pro_monthly_prepaid",".005666666667",3000)])
def test_verified_subscription_allocation_is_not_an_invoice(tier,cost,credits):
    price=policy.price_for("native_transcript",tier,at=date(2026,11,14))
    assert Decimal(price["allocated_unit_usd"])==Decimal(cost)
    assert price["included_credits"]==credits and price["quantity_per_request"]==1
    assert price["estimate_basis"]=="allocated_prepaid_subscription"


@pytest.mark.parametrize("op,tier,provider_name,at",[("generate","free_prepaid","supadata",date(2026,11,14)),("metadata","other","supadata",date(2026,11,14)),("metadata","free_prepaid","deepgram",date(2026,11,14)),("metadata","free_prepaid","supadata",date(2026,11,15)),("metadata","free_prepaid","supadata",date(2026,11,13))])
def test_unknown_operation_tier_provider_or_date_has_no_zero_price(op,tier,provider_name,at):
    with pytest.raises(HTTPException):policy.price_for(op,tier,provider=provider_name,at=at)


def test_overlapping_registry_periods_rejected(tmp_path):
    data=policy.registry();data["entries"].append(data["entries"][0])
    p=tmp_path/"prices.json";p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="Overlapping"):policy.registry(p)


@pytest.mark.parametrize("field,value",[("extraction_enabled",False),("paid_operations_enabled",False),("supadata_prepaid_verified",False),("supadata_auto_recharge_disabled",False),("supadata_api_key",None),("supadata_credit_limit",0),("supadata_credit_limit",3001),("supadata_credit_pool",""),("extraction_max_video_seconds",0),("extraction_max_response_bytes",0),("extraction_max_concurrent_operations",0),("extraction_timeout_seconds",0),("provider_operation_ceiling_usd",".00001"),("user_budget_usd","0"),("global_budget_usd","0"),("supadata_transcript_mode","auto")])
def test_missing_approval_or_bound_is_fail_closed(field,value):
    with pytest.raises(HTTPException):policy.configuration(settings(**{field:value}),at=date(2026,11,14))


@pytest.mark.parametrize("value",[None,False,-1,0,301,float("nan"),float("inf"),"30"])
def test_untrusted_or_out_of_range_duration(value):
    with pytest.raises(policy.ExtractionSafetyError):policy.checked_duration(value,settings())


@pytest.mark.parametrize("url",["http://www.youtube.com/watch?v=a","https://evil.test/a.mp4","https://www.youtube.com.evil.test/watch?v=a","https://user:pass@youtube.com/watch?v=a","https://youtube.com:443/watch?v=a","https://youtube.com/channel/a"])
def test_urls_do_not_allow_files_credentials_redirects_or_playlists(url):
    with pytest.raises(policy.ExtractionSafetyError):policy.input_url(url,"youtube",settings())


@pytest.mark.parametrize("url,platform",[(URL,"youtube"),("https://www.instagram.com/reel/abc/","instagram"),("https://www.facebook.com/reel/1234/","facebook")])
def test_supported_public_video_platforms(url,platform,monkeypatch):
    expected=policy.input_url(url,platform,settings())
    assert expected.startswith("https://www.")
    from app.services import project_service
    monkeypatch.setattr(project_service,"get_settings",lambda:settings())
    assert project_service._normalized_cache_url(url)==expected


def test_preflight_required_and_attempts_are_durable(db_session,owned):
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")
    preflight(db_session,owned)
    first=admit(db_session,owned,"native_transcript")
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")
    accounting.claim(db_session,first,owned[0]);accounting.finish(db_session,first,"safe_failure");db_session.flush()
    second=admit(db_session,owned,"native_transcript")
    accounting.claim(db_session,second,owned[0]);accounting.finish(db_session,second,"safe_failure");db_session.flush()
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")
    assert db_session.scalar(select(func.count()).select_from(ProviderOperation))==3
    assert db_session.get(BudgetAccount,owned[0].user_id).reserved_usd==Decimal(".03")


def test_unknown_outcome_holds_credit_and_blocks_late_settlement(db_session,owned):
    preflight(db_session,owned)
    identifier=admit(db_session,owned,"native_transcript")
    accounting.claim(db_session,identifier,owned[0]);accounting.finish(db_session,identifier,"needs_reconciliation")
    assert not accounting.finish(db_session,identifier,"completed")
    assert balance(db_session,owned[0].user_id)["reserved"]==1
    with pytest.raises(HTTPException):settle(db_session,owned[2].id,"failed",verified_no_active_work=True)
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")
    row=db_session.get(ProviderOperation,identifier)
    assert row.provider_details["estimated_cost_usd"] is None
    assert row.provider_details["actual_billed_cost_usd"] is None


def test_completed_or_unavailable_requests_do_not_retry(db_session,owned):
    identifier=preflight(db_session,owned)
    assert not accounting.finish(db_session,identifier,"unavailable")
    identifier=admit(db_session,owned,"native_transcript")
    accounting.claim(db_session,identifier,owned[0]);accounting.finish(db_session,identifier,"unavailable")
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")


def test_pool_usd_and_concurrency_cannot_be_reset_per_slot(db_session,owned):
    s=owned[-1];s.supadata_credit_limit=1
    preflight(db_session,owned)
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")
    s.supadata_credit_limit=100;s.global_budget_usd=".01"
    with pytest.raises(HTTPException):admit(db_session,owned,"native_transcript")
    s.global_budget_usd="10";s.extraction_max_concurrent_operations=1
    admit(db_session,owned,"native_transcript")
    with pytest.raises(HTTPException):admit(db_session,owned,slot="content_2")


def test_cross_user_slot_and_revoked_worker_cannot_admit(db_session,owned):
    principal,project,_,_,s=owned
    stranger=Principal(str(uuid4()),str(uuid4()),1);provision(db_session,stranger)
    with pytest.raises(HTTPException):accounting.admit(db_session,stranger,project,"content_1",URL,"youtube","metadata",settings=s,rate=False)
    with pytest.raises(HTTPException):accounting.admit(db_session,principal,project,"content_2",URL,"youtube","metadata",settings=s,rate=False)
    identifier=admit(db_session,owned)
    db_session.get(AppUser,principal.user_id).status="suspended";db_session.flush()
    with pytest.raises(policy.ExtractionSafetyError):accounting.claim(db_session,identifier,principal)


def test_recreation_after_known_failed_billing_cannot_buy_free_retries(db_session,owned):
    principal,_,reservation,_,s=owned
    identifier=admit(db_session,owned)
    accounting.finish(db_session,identifier,"unavailable");db_session.flush()
    settle(db_session,reservation.id,"failed",verified_no_active_work=True)
    project=ProjectRepository(db_session).create(project_id=str(uuid4()),content_1_url=URL,content_2_url=OTHER,content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
    new,_=reserve(db_session,principal,project,"bounded-request-2");job=JobRepository(db_session).create(project);new.job_id=job.id
    db_session.add(DispatchOutbox(id=job.id,reservation_id=new.id,task_name="creatorlens.ingest_project",argument=job.id,state="claimed"));db_session.flush()
    with pytest.raises(HTTPException,match="Previous extraction"):
        accounting.admit(db_session,principal,project,"content_1",URL,"youtube","metadata",settings=s,rate=False)


def test_usage_allowlist_has_no_credentials_or_raw_provider_data(db_session,owned):
    identifier=admit(db_session,owned)
    row=db_session.get(ProviderOperation,identifier)
    row.provider_details=dict(row.provider_details,raw_headers="never-export",url="private-url")
    public=accounting.public_operation(row)
    assert "raw_headers" not in public and "url" not in public and "source_key" not in public
    assert public["actual_billed_cost_usd"] is None and public["provider"]=="supadata"


def fake_transport(monkeypatch,handler):
    original=httpx.Client
    def client(**kwargs):
        assert kwargs["follow_redirects"] is False and kwargs["trust_env"] is False
        def streaming(request):
            response=handler(request)
            return httpx.Response(response.status_code,headers=response.headers,stream=httpx.ByteStream(response.content))
        kwargs["transport"]=httpx.MockTransport(streaming)
        return original(**kwargs)
    monkeypatch.setattr(provider.httpx,"Client",client)


def metadata():
    return {"platform":"youtube","type":"video","url":URL,"title":"Synthetic education", "media":{"duration":30},"stats":{"views":1234,"likes":20,"comments":3}}


def test_native_metadata_transcript_pipeline_and_no_audio_fallback(db_session,owned,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("metadata"):return httpx.Response(200,json=metadata())
        assert request.url.params["mode"]=="native" and request.url.params["lang"]=="en"
        return httpx.Response(200,json={"lang":"en","content":[{"text":"Learn a specific topic today.","offset":0,"duration":8000}]})
    fake_transport(monkeypatch,handler)
    result=provider.extract(owned[1],"content_1","youtube",URL)
    assert len(calls)==2 and result.metadata.views==1234
    assert result.metadata.subscriber_count is None
    assert result.metadata.transcript_evidence["provenance"]["audio_language_verified"] is False
    assert result.metadata.transcript_language=="en" and provider.compatible_cache(result,owned[-1])
    assert all(op.state=="completed" for op in db_session.scalars(select(ProviderOperation)))


@pytest.mark.parametrize("outcome",["timeout","async","redirect","oversized","malformed","server_error"])
def test_uncertain_outcomes_never_poll_retry_or_fake_zero(db_session,owned,monkeypatch,outcome):
    calls=[]
    def handler(request):
        calls.append(request)
        if outcome=="timeout":raise httpx.ReadTimeout("fixture timeout")
        if outcome=="async":return httpx.Response(202,json={"jobId":"not-polled"})
        if outcome=="redirect":return httpx.Response(302,headers={"Location":"https://elsewhere.test"})
        if outcome=="oversized":return httpx.Response(200,content=b" "*20000)
        if outcome=="malformed":return httpx.Response(200,content=b"not-json")
        return httpx.Response(503)
    fake_transport(monkeypatch,handler)
    with pytest.raises(policy.ExtractionSafetyError):provider.request(owned[1],"content_1",URL,"youtube","metadata")
    assert len(calls)==1 and owned[2].state=="needs_reconciliation"
    row=db_session.scalar(select(ProviderOperation))
    assert row.reserved_quantity==1 and row.provider_details["actual_billed_cost_usd"] is None


@pytest.mark.parametrize("status",[400,401,402,403,404,429])
def test_confirmed_rejection_preserves_exposure_without_paid_retry(db_session,owned,monkeypatch,status):
    fake_transport(monkeypatch,lambda req:httpx.Response(status))
    assert provider.request(owned[1],"content_1",URL,"youtube","metadata") is None
    row=db_session.scalar(select(ProviderOperation))
    assert row.state=="unavailable" and row.reserved_quantity==1
    assert row.provider_details["actual_billed_cost_usd"] is None


def test_stale_running_operation_and_claim_only_crash_require_review(db_session,owned):
    from app.services.usage_reconciliation import mark_uncertain_operations
    identifier=admit(db_session,owned);accounting.claim(db_session,identifier,owned[0])
    row=db_session.get(ProviderOperation,identifier);row.created_at=datetime.now(UTC)-timedelta(minutes=20);db_session.flush()
    assert mark_uncertain_operations(db_session)==1 and row.state=="needs_reconciliation"
    assert not accounting.finish(db_session,identifier,"completed")


def test_duplicate_worker_delivery_claims_outbox_once(db_session,owned,monkeypatch):
    from app.workers import owned_execution as worker
    @contextmanager
    def database():
        yield db_session
        db_session.flush()
    monkeypatch.setattr(worker,"get_settings",lambda:owned[-1]);monkeypatch.setattr(worker,"database_session",database)
    outbox=db_session.get(DispatchOutbox,owned[3].id);outbox.state="sent";db_session.flush()
    calls=[]
    @worker.owned_task("extraction")
    def run(job_id):calls.append(job_id);return {"status":"chunking"}
    assert run(owned[3].id)=={"status":"chunking"}
    assert run(owned[3].id)=={"status":"deduplicated"} and calls==[owned[3].id]


@pytest.mark.parametrize("module,name,args",[("app.services.supadata_transcript_service","_fetch_transcript_payload",()),("app.services.apify_transcript_service","_run_actor",()),("app.services.transcription_service","transcribe_audio_url_with_deepgram",("https://private.test/audio",)),("app.extractors.youtube_extractor","fetch_youtube_info",(URL,)),("app.extractors.instagram_extractor","fetch_instagram_info",("https://instagram.com/reel/a/",)),("app.extractors.facebook_extractor","fetch_facebook_info",("https://facebook.com/reel/1/",))])
def test_legacy_network_paths_are_disabled_in_authenticated_mode(monkeypatch,module,name,args):
    import importlib
    import app.core.config as config
    monkeypatch.setattr(config,"get_settings",lambda:settings())
    function=getattr(importlib.import_module(module),name)
    # Internal keyword signatures are supplied explicitly; guards run before transport.
    if name=="_fetch_transcript_payload":
        with pytest.raises(policy.ExtractionSafetyError):function(url=URL,api_key="fixture",mode="auto",timeout_seconds=5)
    elif name=="_run_actor":
        import inspect
        parameters=inspect.signature(function).parameters
        values={key:("fixture" if "token" in key or "actor" in key else 5 if "timeout" in key else {}) for key in parameters}
        with pytest.raises(policy.ExtractionSafetyError):function(**values)
    else:
        with pytest.raises(policy.ExtractionSafetyError):function(*args)


@pytest.mark.parametrize("tier,interval",[("free_prepaid",1100),("pro_monthly_prepaid",110)])
def test_provider_pacing_is_shared_by_account_pool(tier,interval):
    from app.extraction.dispatch_limit import enforce_provider_rate
    calls=[]
    class Redis:
        def set(self,key,value,**kwargs):calls.append((key,kwargs));return True
    enforce_provider_rate(settings(supadata_billing_tier=tier),connection=Redis())
    assert calls[0][1]=={"nx":True,"px":interval}
    assert "offline-fixture-pool" not in calls[0][0]


def test_provider_pacing_outage_does_not_admit_work():
    from app.extraction.dispatch_limit import enforce_provider_rate
    class Down:
        def set(self,*args,**kwargs):raise ConnectionError("private details")
    with pytest.raises(policy.ExtractionSafetyError,match="no external request sent"):
        enforce_provider_rate(settings(),connection=Down())


def test_pre_send_retry_is_one_shared_slot_allowance(db_session,owned,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("metadata"):return httpx.Response(200,json=metadata())
        if len(calls)==2:raise httpx.PoolTimeout("local pool exhausted before send")
        return httpx.Response(200,json={"lang":"en","content":[{"text":"A synthetic explanation.","offset":0,"duration":5000}]})
    fake_transport(monkeypatch,handler)
    result=provider.extract(owned[1],"content_1","youtube",URL)
    assert len(calls)==3 and result.metadata.transcript_available
    operations=db_session.scalars(select(ProviderOperation).where(ProviderOperation.kind=="extraction").order_by(ProviderOperation.attempt)).all()
    assert [(op.attempt,op.state) for op in operations]==[(1,"safe_failure"),(2,"completed")]
    assert sum(op.reserved_quantity for op in operations)==2
    assert operations[0].provider_details["estimated_cost_usd"]=="0"
    assert operations[0].provider_details["known_billable_quantity"]==0


@pytest.mark.parametrize("duration",[None,0,301])
def test_metadata_duration_rejection_never_starts_transcription(db_session,owned,monkeypatch,duration):
    calls=[]
    def handler(request):
        calls.append(request);payload=metadata();payload["media"]["duration"]=duration
        return httpx.Response(200,json=payload)
    fake_transport(monkeypatch,handler)
    with pytest.raises(policy.ExtractionSafetyError):provider.extract(owned[1],"content_1","youtube",URL)
    assert len(calls)==1
    assert db_session.scalar(select(ProviderOperation)).state=="unavailable"


def test_provider_kill_switch_checked_before_any_transport_or_new_attempt(db_session,owned,monkeypatch):
    owned[-1].paid_operations_enabled=False
    monkeypatch.setattr(provider.httpx,"Client",lambda **kwargs:pytest.fail("Transport must not be constructed."))
    with pytest.raises(HTTPException):provider.request(owned[1],"content_1",URL,"youtube","metadata")
    assert db_session.scalar(select(func.count()).select_from(ProviderOperation))==0


def test_crash_before_first_provider_operation_is_reviewed(db_session,owned):
    from app.services.usage_reconciliation import mark_uncertain_operations
    from app.services.account_usage import event
    from app.db.models.account import UsageEvent
    event(db_session,owned[0].user_id,"ingestion_claimed",owned[3].id)
    claim=db_session.scalar(select(UsageEvent).where(UsageEvent.kind=="ingestion_claimed"))
    owned[2].state="processing";db_session.flush()
    assert mark_uncertain_operations(db_session,now=datetime.now(UTC)+timedelta(minutes=20))==0
    assert owned[2].state=="needs_reconciliation" and balance(db_session,owned[0].user_id)["reserved"]==1
    assert owned[3].status=="FAILED" and owned[3].error_code=="NEEDS_RECONCILIATION"


def test_compatible_cache_avoids_provider_requests(db_session,owned,monkeypatch):
    from app.services import project_service as service
    from app.models.video import VideoMetadata,VideoExtractionResult,TranscriptSegment
    from app.services.evidence_quality import validate_extraction
    result=validate_extraction(VideoExtractionResult(metadata=VideoMetadata(platform="youtube",url=URL,duration_seconds=30,views=1234,transcript_source="supadata_platform_captions",extraction_status="partial",transcript_evidence={"provenance":{"extraction_policy":policy.POLICY_VERSION}}),transcript_segments=[TranscriptSegment(segment_index=0,start_time=0,end_time=8,text="A synthetic cached explanation.")]))
    monkeypatch.setattr(service,"get_settings",lambda:owned[-1])
    monkeypatch.setattr(service,"_cached_extraction_result",lambda url:result)
    monkeypatch.setattr(service,"_extract_url",lambda **kwargs:pytest.fail("Cache hit must not invoke a provider."))
    monkeypatch.setattr(service,"get_video_by_project_slot",lambda *args:None)
    monkeypatch.setattr(service,"upsert_video_metadata",lambda **kwargs:{"id":"synthetic-content-id"})
    for name in ("replace_transcript_segments","update_content_cache_identity","update_content_cache_observation"):
        monkeypatch.setattr(service,name,lambda *args,**kwargs:None)
    assert service._extract_and_store_platform(owned[1],"content_1","youtube",URL)=="partial"
    assert db_session.scalar(select(func.count()).select_from(ProviderOperation))==0


def test_additive_migration_renders_postgresql_sql_and_one_head():
    import importlib.util
    from io import StringIO
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    root=Path(__file__).parents[2]
    config=Config(str(root/"alembic.ini"));config.set_main_option("script_location",str(root/"alembic"))
    assert ScriptDirectory.from_config(config).get_heads()==["20261114_0013"]
    spec=importlib.util.spec_from_file_location("extraction_revision",root/"alembic/versions/20261114_0013_extraction_accounting.py")
    revision=importlib.util.module_from_spec(spec);spec.loader.exec_module(revision)
    output=StringIO()
    context=MigrationContext.configure(dialect_name="postgresql",opts={"as_sql":True,"output_buffer":output})
    with Operations.context(context):revision.upgrade()
    sql=output.getvalue()
    assert "CREATE UNIQUE INDEX uq_provider_operations_operation_key" in sql
    assert "provider_quantity_nonnegative" in sql
    assert "DROP" not in sql and "UPDATE" not in sql and "DELETE" not in sql
    assert revision.down_revision=="20261114_0012"


@pytest.mark.parametrize("unknown",[False,True])
def test_worker_failure_preserves_unknowns_and_releases_only_known_inactive_work(db_session,owned,monkeypatch,unknown):
    from app.workers import job_runtime as runtime
    from app.workers.job_runtime import WorkerTaskFailedError
    identifier=admit(db_session,owned)
    accounting.claim(db_session,identifier,owned[0])
    accounting.finish(db_session,identifier,"needs_reconciliation" if unknown else "unavailable")
    @contextmanager
    def database():yield db_session;db_session.flush()
    monkeypatch.setattr(runtime,"get_settings",lambda:owned[-1])
    monkeypatch.setattr(runtime,"database_session",database)
    monkeypatch.setattr(runtime,"safe_worker_error",lambda exc,**kwargs:"Synthetic failure")
    with pytest.raises(WorkerTaskFailedError):
        runtime.retry_or_fail_job(SimpleNamespace(),job_id=owned[3].id,project_id=owned[1],exc=policy.ExtractionSafetyError("Synthetic failure"),error_code="TEST",fallback_message="Synthetic failure")
    assert owned[2].state==("needs_reconciliation" if unknown else "failed")
    assert balance(db_session,owned[0].user_id)["reserved"]==(1 if unknown else 0)
    assert db_session.get(BudgetAccount,owned[0].user_id).reserved_usd==Decimal(".01")
