"""Mocked semantic extraction: no provider calls or external resources."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import json
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.insights.semantic_models import FEATURES, CreativeFeatures
from app.insights.semantic_evidence import build_semantic_input, parse_features
from app.insights.semantic_scoring import semantic_creative_score, apply_semantic_scoring
from app.insights.deterministic_scoring import calculate_scoring
from app.db.models.semantic_snapshot import SemanticSnapshot
from app.db.repositories import semantic_repository as store
from app.services import semantic_service as service

@pytest.fixture
def content():
    item = dict(id='video-a',slot='content_1',platform='youtube',duration_seconds=12,title='Dopamine and habits',
        description='Subscribe for another explanation.', views=34021,likes=485,comments=8,
        transcript_source='captions', transcript_evidence={'status':'valid','revision':'revision-a',
            'provenance':{'original_audio_language':'en','caption_track_language':'en','transcript_language':'en','caption_kind':'original'}})
    segments=[dict(segment_index=0,start_time=0.,end_time=4.,text='Why does dopamine affect your habits?'),
        dict(segment_index=1,start_time=4.,end_time=8.,text='For students, understand a practical response to distraction.'),
        dict(segment_index=2,start_time=8.,end_time=12.,text='The problem is distraction; try a timed break. Subscribe for more.')]
    return item,segments


def context(content):
    return build_semantic_input('project-a',*content)


def answer(ctx):
    refs={kind:next((s for s in ctx['sources'] if s['source_type']==kind),None) for kind in ('opening','transcript','description')}
    features=[]
    for name in FEATURES:
        kind='opening' if name in {'opening_type','verbal_hook_clarity','topic_specificity','curiosity_gap'} else 'description' if name=='description_cta' else 'transcript'
        src=refs[kind]
        features.append(dict(feature=name,value='question' if name=='opening_type' else 'clear',status='assessed',
            evidence=[dict(evidence_id=src['id'],content_id=ctx['content_id'],slot=ctx['slot'],excerpt=src['text'],start_time=src['start_time'],end_time=src['end_time'])] if src else []))
    return dict(schema_version='creative-features-1.0.0',project_id=ctx['project_id'],content_id=ctx['content_id'],slot=ctx['slot'],input_revision=ctx['input_revision'],features=features)

@pytest.mark.parametrize('opening,label',[
    ('Why does dopamine affect your habits?','question'),('Dopamine helps explain habits.','introduction'),
    ('Here is something.','other'),('A student can reduce distraction with timed breaks.','problem')])
def test_opening_labels_are_grounded_not_keyword_scores(content,opening,label):
    content[1][0]['text']=opening
    ctx=context(content); data=answer(ctx);data['features'][0]['value']=label
    result=parse_features(json.dumps(data),ctx)
    assert result.features[0].value==label

@pytest.mark.parametrize('change', ['id','slot','content','excerpt','timestamp','source_type','revision','unknown_feature','missing','score','label','coverage'])
def test_rejects_unsupported_model_assertions(content,change):
    ctx=context(content); data=answer(ctx); ref=data['features'][0]['evidence'][0]
    if change=='id':ref['evidence_id']='invented'
    elif change=='slot':ref['slot']='content_2'
    elif change=='content':ref['content_id']='video-b'
    elif change=='excerpt':ref['excerpt']='Invented retention evidence'
    elif change=='timestamp':ref['end_time']=1.
    elif change=='source_type':ref['evidence_id']=next(s['id'] for s in ctx['sources'] if s['source_type']=='description')
    elif change=='revision':data['input_revision']='stale'
    elif change=='unknown_feature':data['features'][0]['feature']='visual_quality'
    elif change=='missing':data['features'].pop()
    elif change=='score':data['winner']='content_1'
    elif change=='label':data['features'][1]['value']='excellent'
    elif change=='coverage':data['features'][-1]['value']='partial'
    with pytest.raises(ValueError):parse_features(json.dumps(data),ctx)

@pytest.mark.parametrize('raw',['not json','{}','```json\n{}\n```','{"features":null}'])
def test_malformed_response_fails(content,raw):
    with pytest.raises(ValueError):parse_features(raw,context(content))


def test_spoken_and_description_cta_cannot_cross_sources(content):
    ctx=context(content);data=answer(ctx)
    spoken=next(f for f in data['features'] if f['feature']=='spoken_cta')
    desc=next(f for f in data['features'] if f['feature']=='description_cta')
    spoken['evidence']=desc['evidence']
    with pytest.raises(ValueError):parse_features(json.dumps(data),ctx)

@pytest.mark.parametrize('case',['music','missing','unknown_language','boundary','partial'])
def test_evidence_limits_are_preserved(content,case):
    item,segments=content
    if case=='music':
        for s in segments:s['text']='[music]'
    elif case=='missing':segments.clear()
    elif case=='unknown_language':item['transcript_evidence']['provenance']={}
    elif case=='boundary':segments[:]=[dict(segment_index=0,start_time=0.,end_time=12.,text='A long sentence that crosses the opening window.')]
    else:item['transcript_evidence']['status']='partial'
    ctx=context(content)
    if case in {'music','missing','unknown_language'}:assert not any(s['source_type']=='transcript' for s in ctx['sources'])
    if case=='boundary':assert not any(s['source_type']=='opening' for s in ctx['sources'])
    if case=='partial':assert not ctx['complete']


def test_partial_evidence_cannot_establish_absence(content):
    content[0]['transcript_evidence']['status']='partial'
    ctx=context(content);data=answer(ctx);data['features'][-1]['value']='partial';data['features'][7]['value']='absent'
    with pytest.raises(ValueError):parse_features(json.dumps(data),ctx)


def test_missing_feature_does_not_become_weak_hook(content):
    ctx=context(content);data=answer(ctx)
    data['features'][1].update(value='unassessable',status='unassessable',evidence=[])
    features=parse_features(json.dumps(data),ctx)
    score=semantic_creative_score(features)
    assert score.score is None
    assert next(p for p in score.components if p.feature=='verbal_hook_clarity').score is None


def test_fixed_labels_reproduce_scores_without_changing_metric_policy(content):
    ctx=context(content);features=parse_features(json.dumps(answer(ctx)),ctx)
    base=calculate_scoring(content[0],dict(hook_clarity=2,problem_solution_clarity=3,caption_strength=4,cta_strength=5,audience_specificity=6),hook_assessable=True)
    before=base.model_dump_json()
    first=apply_semantic_scoring(base,features,'snapshot')
    assert first==apply_semantic_scoring(base,features,'snapshot')
    assert first.creative_structure.score==10
    assert first.reach==base.reach and first.public_performance==base.public_performance
    assert first.metric_policy_version=='creator-insight-2.0.0'
    assert first.creative_policy_version=='semantic-creative-1.0.0'
    assert base.model_dump_json()==before
    assert first.authoritative_winner is None

@pytest.fixture
def runtime(monkeypatch,content):
    folder = TemporaryDirectory(prefix="semantic-test-", dir=Path.cwd())
    tmp_path = Path(folder.name)
    engine=create_engine('sqlite+pysqlite:///'+str(tmp_path/'semantic.db'),connect_args={'check_same_thread':False})
    SemanticSnapshot.__table__.create(engine)
    @contextmanager
    def session(**kwargs):
        with Session(engine,expire_on_commit=False) as s:
            with s.begin():yield s
    monkeypatch.setattr(store,'semantic_session',session)
    monkeypatch.setattr(service,'get_project_detail_record',lambda _:dict(content_items=[content[0]]))
    monkeypatch.setattr(service,'get_transcript_segments',lambda **_:content[1])
    from app.workers.semantic_tasks import extract_semantic_features
    dispatched=[]
    monkeypatch.setattr(extract_semantic_features,'apply_async',lambda **kw:dispatched.append(kw))
    for name in ('start_llm_run','complete_llm_run','fail_llm_run','record_cost_event'):
        monkeypatch.setattr(service,name,lambda *args,**kwargs:None)
    calls=[]
    async def invoke(ctx,prompt):
        calls.append(ctx)
        return SimpleNamespace(content=json.dumps(answer(ctx)),usage_metadata={'input_tokens':100,'output_tokens':200,'total_tokens':300})
    monkeypatch.setattr(service,'_invoke',invoke)
    yield calls,dispatched
    engine.dispose()
    folder.cleanup()


def test_cached_get_never_invokes_gemini_and_jobs_are_idempotent(runtime):
    calls,dispatched=runtime
    assert service.get_semantic_analysis('project-a','content_1')['status']=='unavailable'
    pending=service.queue_semantic_analysis('project-a','content_1')
    assert pending['status']=='pending' and not calls
    key=pending['snapshot_id']
    assert service.process_semantic_snapshot(key)['status']=='ready'
    for _ in range(3):assert service.get_semantic_analysis('project-a','content_1')['cache_hit']
    assert service.process_semantic_snapshot(key)['status']=='deduplicated'
    service.queue_semantic_analysis('project-a','content_1')
    assert len(calls)==1 and len(dispatched)==1
    assert store.read_snapshot(key)['processing']['token_usage']['total_tokens']==300


def test_evidence_revision_invalidates_cache_without_deleting_success(runtime,content):
    old=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    service.process_semantic_snapshot(old)
    content[0]['transcript_evidence']['revision']='corrected'
    assert service.get_semantic_analysis('project-a','content_1')['status']=='unavailable'
    assert store.read_snapshot(old)['status']=='ready'
    new=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    assert new!=old


def test_concurrent_claim_allows_one_worker(runtime):
    key=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:store.claim_snapshot(key),range(2)))
    assert results.count(True)==1

@pytest.mark.parametrize('failure',[TimeoutError('timeout'),RuntimeError('429 rate limited'),ValueError('malformed')])
def test_failure_is_bounded_and_does_not_break_other_work(runtime,monkeypatch,failure):
    async def bad(*args):raise failure
    monkeypatch.setattr(service,'_invoke',bad)
    key=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    for _ in range(2):
        assert service.process_semantic_snapshot(key)['status']=='failed'
        service.queue_semantic_analysis('project-a','content_1',retry_failed=True)
    assert store.read_snapshot(key)['attempts']==2
    assert service.process_semantic_snapshot(key)['status']=='deduplicated'


def test_stale_queued_input_never_invokes_gemini(runtime,content):
    calls,_=runtime
    key=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    content[1][0]['text']='Changed evidence'
    assert service.process_semantic_snapshot(key)['error_code']=='STALE_INPUT'
    assert not calls


def test_queue_failures_and_missing_evidence_are_explicit(runtime,content,monkeypatch):
    from app.workers.semantic_tasks import extract_semantic_features
    def fail(**kwargs):raise RuntimeError('broker unavailable')
    monkeypatch.setattr(extract_semantic_features,'apply_async',fail)
    assert service.queue_semantic_analysis('project-a','content_1')['error_code']=='QUEUE_UNAVAILABLE'
    content[1].clear()
    assert service.queue_semantic_analysis('project-a','content_1')['status']=='unavailable'


def test_explicit_cost_authorization_required():
    from app.api.semantic import queue_semantic
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:queue_semantic('project-a','content_1')
    assert error.value.status_code==422

def test_unknown_or_translated_language_never_generates_semantic_context(content):
    item,segments=content
    item['transcript_evidence']['provenance']['transcript_language']='zz'
    assert not context(content)['sources']
    item['transcript_evidence']['provenance']['transcript_language']='en'
    item['transcript_evidence']['provenance']['caption_kind']='translated'
    assert not context(content)['sources']


def test_context_budget_limits_segment_overhead_and_discloses_truncation(content):
    item,_=content
    item['duration_seconds']=100
    segments=[dict(segment_index=i,start_time=float(i),end_time=float(i+1),text='Word') for i in range(100)]
    ctx=build_semantic_input('project-a',item,segments)
    assert len(ctx['sources'])<=41 and not ctx['complete']
    assert 'context_budget_truncated' in ctx['limitations']


def test_label_mapping_partial_absent_and_coverage_are_deterministic(content):
    ctx=context(content);data=answer(ctx)
    for feature in data['features']:
        if feature['feature'] in {'curiosity_gap','spoken_cta'}:feature['value']='partial'
        if feature['feature']=='description_cta':feature['value']='absent'
    score=semantic_creative_score(parse_features(json.dumps(data),ctx))
    assert score.score==pytest.approx(8.75)
    assert sum(c.contribution or 0 for c in score.components)==pytest.approx(score.score)


def test_ordinary_insight_get_reads_cached_features_without_inference(runtime,monkeypatch,content):
    from app.insights import insight_service
    key=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    service.process_semantic_snapshot(key)
    monkeypatch.setattr(insight_service,'get_transcript_segments',lambda **_:content[1])
    def forbidden(*args,**kwargs):raise AssertionError('GET must not create an LLM')
    monkeypatch.setattr(service,'get_llm',forbidden)
    result=insight_service._build_content_insight('project-a',content[0])
    assert result.semantic_analysis['status']=='ready'
    assert result.semantic_scoring.creative_structure.score==10
    assert result.scoring.policy.version=='creator-insight-2.0.0'
    assert result.scores.policy_version=='legacy-1.0.0'


def test_late_attempt_cannot_replace_newer_worker_result(runtime):
    key=service.queue_semantic_analysis('project-a','content_1')['snapshot_id']
    assert store.claim_snapshot(key)
    assert store.transition(key,'running','failed',attempt=1,error_code='INTERRUPTED')
    assert store.transition(key,'failed','pending')
    assert store.claim_snapshot(key)
    assert not store.transition(key,'running','ready',attempt=1,result={'stale':True})
    assert store.read_snapshot(key)['status']=='running'


def test_sdk_generation_limits_reuse_existing_client(monkeypatch,content):
    calls=[]
    class Fake:
        async def ainvoke(self,messages,**kwargs):
            calls.append(kwargs)
            return 'response'
    options=[]
    monkeypatch.setattr(service,'get_llm',lambda **kwargs:(options.append(kwargs) or Fake()))
    import asyncio
    ctx=context(content)
    asyncio.run(service._invoke(ctx,{'system_prompt':'test'}))
    assert options[0]['max_retries']==0 and options[0]['timeout']==60
    assert options[0]['temperature']==0 and options[0]['max_output_tokens']==4096
    assert calls[0]['response_mime_type']=='application/json'
