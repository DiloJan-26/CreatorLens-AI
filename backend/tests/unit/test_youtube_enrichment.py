"""Mocked official API boundaries; no quota/account credentials or network access."""
from contextlib import contextmanager
from types import SimpleNamespace
import httpx
import pytest
from app.extraction import youtube_enrichment as enrichment
from tests.unit.test_bounded_extraction import owned  # reuse isolated ownership fixture


def setup(owned,db_session,monkeypatch,handler,**overrides):
    settings=SimpleNamespace(youtube_metadata_enrichment_enabled=True,provider_emergency_stop=False,youtube_api_key='synthetic',redis_url='redis://fixture',
        youtube_enrichment_daily_units=2,extraction_timeout_seconds=2,extraction_max_response_bytes=8192)
    for k,v in overrides.items():setattr(settings,k,v)
    @contextmanager
    def database():yield db_session
    monkeypatch.setattr(enrichment,'database_session',database)
    monkeypatch.setattr(enrichment,'enforce_rate',lambda *a:None)
    monkeypatch.setattr(enrichment,'client',lambda *a:SimpleNamespace(eval=lambda *a:1))
    original=httpx.Client
    monkeypatch.setattr(enrichment.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler)))
    return settings

def response(request,views='1000',likes='20',comments='3'):
    if request.url.path.endswith('/channels'):return httpx.Response(200,json={'items':[{'id':'channel','statistics':{'subscriberCount':'100'}}]})
    return httpx.Response(200,json={'items':[{'id':'video','statistics':{'viewCount':views,'likeCount':likes,'commentCount':comments},'snippet':{'channelId':'channel','publishedAt':'2024-01-01T00:00:00Z'}}]})

def test_official_snapshot_fills_gap_atomically(owned,db_session,monkeypatch):
    s=setup(owned,db_session,monkeypatch,response)
    old={'view_count':999,'like_count':19,'comment_count':None}
    new,provenance=enrichment.enrich(owned[1],'https://www.youtube.com/watch?v=video',old,s)
    assert (new['view_count'],new['like_count'],new['comment_count'])==(1000,20,3)
    assert old=={'view_count':999,'like_count':19,'comment_count':None}
    assert provenance['previous_count_snapshot']['view_count']==999
    assert new['subscriber_count']==100 and provenance['subscriber_count']['provider']=='youtube_data_api'

def test_incomplete_official_snapshot_cannot_mix_or_erase_existing_counts(owned,db_session,monkeypatch):
    s=setup(owned,db_session,monkeypatch,lambda r:response(r,likes=None))
    old={'view_count':999,'like_count':19,'comment_count':None}
    new,_=enrichment.enrich(owned[1],'https://www.youtube.com/watch?v=video',old,s)
    assert new['like_count']==19 and new['comment_count'] is None and new['view_count']==999

@pytest.mark.parametrize('change',[{'provider_emergency_stop':True},{'youtube_metadata_enrichment_enabled':False},{'youtube_api_key':None}])
def test_disabled_or_unconfigured_enrichment_never_calls_provider(owned,db_session,monkeypatch,change):
    def forbidden(r):raise AssertionError('No HTTP request permitted')
    s=setup(owned,db_session,monkeypatch,forbidden,**change)
    old={'view_count':999};new,provenance=enrichment.enrich(owned[1],'https://www.youtube.com/watch?v=video',old,s)
    assert new==old and provenance=={}

def test_exhausted_quota_preserves_primary_snapshot(owned,db_session,monkeypatch):
    calls=[]
    s=setup(owned,db_session,monkeypatch,lambda r:calls.append(r))
    monkeypatch.setattr(enrichment,'client',lambda *a:SimpleNamespace(eval=lambda *a:3))
    old={'view_count':999};new,provenance=enrichment.enrich(owned[1],'https://www.youtube.com/watch?v=video',old,s)
    assert not calls and new==old and provenance['enrichment_status']=='partial_or_unavailable'

def test_wrong_project_rejected_before_http(owned,db_session,monkeypatch):
    from fastapi import HTTPException
    s=setup(owned,db_session,monkeypatch,response)
    with pytest.raises(HTTPException):enrichment.enrich('another-project','https://www.youtube.com/watch?v=video',{},s)

def test_failed_provider_preserves_primary_snapshot(owned,db_session,monkeypatch):
    s=setup(owned,db_session,monkeypatch,lambda r:httpx.Response(403))
    old={'view_count':999};new,_=enrichment.enrich(owned[1],'https://www.youtube.com/watch?v=video',old,s)
    assert new==old


def test_production_configuration_defaults_to_enabled_with_explicit_opt_out():
    from app.core.config import Settings
    assert Settings(_env_file=None).youtube_metadata_enrichment_enabled is True
    assert Settings(_env_file=None,YOUTUBE_METADATA_ENRICHMENT_ENABLED=False).youtube_metadata_enrichment_enabled is False
    assert Settings(_env_file=None).youtube_enrichment_daily_units==100
