"""Offline usage, money, population and historical compatibility regression fixtures."""
from decimal import Decimal
from datetime import date
from types import SimpleNamespace
import pytest
from app.llm.token_usage import TokenUsage, parse_token_usage
from app.llm.cost_estimation import estimate_model_cost
from app.llm.operation_analytics import operation_analytics, distribution
from app.db.repositories.cost_repository import CostRepository
from app.db.repositories.llm_run_repository import LlmRunRepository
from tests.unit.test_content_item_repository import _create_project


def usage():
    return parse_token_usage({'usage_metadata':{'input_tokens':6803,'output_tokens':946,'total_tokens':7749,
        'input_token_details':{'cache_read':0},'output_token_details':{'reasoning':0}}})


def price(value=None,**kwargs):
    return estimate_model_cost(value or usage(),provider='gemini',model=kwargs.pop('model','gemini-3.5-flash-lite'),
        service_tier=kwargs.pop('service_tier','standard'),at=kwargs.pop('at',date(2026,11,13)),**kwargs)


def test_operation_observability_exact_paid_equivalent_fixture():
    result=price()
    assert result['status']=='estimated'
    assert Decimal(result['components']['input_cost_usd'])==Decimal('.0020409')
    assert Decimal(result['components']['output_cost_usd'])==Decimal('.0023650')
    assert Decimal(result['estimated_cost_usd'])==Decimal('.0044059')
    assert result['actual_billed_cost_usd'] is None
    assert result['policy_version']=='gemini-token-rates-2026-11-13'


@pytest.mark.parametrize('changes',[{'model':'unknown'},{'model':'gemini-3.5-flash'},{'model':'gemini-3.5-flash-lite-latest'},
    {'service_tier':None},{'service_tier':'free'},{'service_tier':'flex'},{'service_tier':'priority'},{'at':date(2026,11,12)}])
def test_operation_observability_never_guesses_model_tier_or_historical_rates(changes):
    result=price(**changes)
    assert result['status']=='pricing_unavailable' and result['estimated_cost_usd'] is None


@pytest.mark.parametrize('shape', ['camel','snake','object'])
def test_operation_observability_native_thinking_cache_and_total(shape):
    data={'promptTokenCount':100,'cachedContentTokenCount':20,'candidatesTokenCount':30,'thoughtsTokenCount':10,'totalTokenCount':140,'serviceTier':'standard'}
    if shape=='snake':
        data=dict(prompt_token_count=100,cached_content_token_count=20,candidates_token_count=30,thoughts_token_count=10,total_token_count=140,service_tier='standard')
    response=SimpleNamespace(usage_metadata=data) if shape=='object' else {'usageMetadata':data}
    value=parse_token_usage(response)
    assert value.input_tokens==100 and value.cached_input_tokens==20 and value.noncached_input_tokens==80
    assert value.candidate_tokens==30 and value.thinking_tokens==10 and value.output_tokens==40
    assert value.total_tokens==value.provider_total_tokens==140 and value.completeness=='complete'
    result=price(value,caching_mode='implicit')
    assert Decimal(result['estimated_cost_usd'])==Decimal('.0001246')


def test_operation_observability_combined_langchain_does_not_add_reasoning_twice():
    value=parse_token_usage({'usage_metadata':{'input_tokens':100,'output_tokens':40,'total_tokens':140,
        'input_token_details':{'cache_read':20},'output_token_details':{'reasoning':10}}})
    assert value.output_tokens==40 and value.candidate_tokens==30 and value.thinking_tokens==10
    assert Decimal(price(value,caching_mode='implicit')['estimated_cost_usd'])==Decimal('.0001246')


@pytest.mark.parametrize('bad',[-1,True,1.5,'invalid',float('inf')])
def test_operation_observability_invalid_integral_counts_are_unavailable(bad):
    value=parse_token_usage({'usage_metadata':{'input_tokens':bad,'output_tokens':4,'input_token_details':{'cache_read':0}}})
    assert value.input_tokens is None and value.completeness=='partial' and value.warnings
    assert price(value)['estimated_cost_usd'] is None


@pytest.mark.parametrize('data',[{}, {'input_tokens':10},{'output_tokens':10},{'input_tokens':10,'output_tokens':2},
    {'promptTokenCount':10,'candidatesTokenCount':2}, {'promptTokenCount':10,'candidatesTokenCount':2,'totalTokenCount':19},
    {'promptTokenCount':10,'cachedContentTokenCount':20,'candidatesTokenCount':2,'thoughtsTokenCount':0,'totalTokenCount':12}])
def test_operation_observability_partial_unknown_and_inconsistent_usage_is_not_complete_cost(data):
    assert price(parse_token_usage({'usage_metadata':data}))['estimated_cost_usd'] is None


def test_operation_observability_tool_prompt_tokens_reconcile_but_charges_remain_partial():
    value=parse_token_usage({'usageMetadata':{'promptTokenCount':100,'cachedContentTokenCount':0,'candidatesTokenCount':20,
        'thoughtsTokenCount':5,'toolUsePromptTokenCount':7,'totalTokenCount':132}})
    assert value.total_tokens==132 and value.output_tokens==25 and not value.warnings
    result=price(value)
    assert result['status']=='partial' and result['estimated_cost_usd'] is None


def test_operation_observability_explicit_cache_storage_is_not_silently_free():
    value=parse_token_usage({'usage_metadata':{'input_tokens':100,'output_tokens':20,'input_token_details':{'cache_read':10}}})
    assert price(value)['status']=='partial'
    assert price(value,caching_mode='implicit')['status']=='estimated'


def test_operation_observability_one_token_and_deterministic_zero_are_distinct():
    value=parse_token_usage({'usage_metadata':{'input_tokens':1,'output_tokens':0,'input_token_details':{'cache_read':0}}})
    assert Decimal(price(value)['estimated_cost_usd'])==Decimal('.0000003')
    assert price(deterministic=True)['status']=='known_zero'
    assert price(TokenUsage())['estimated_cost_usd'] is None


def record(session,project,*,cost=None,det=False,latency=9320,op=None,known_invocation=True):
    run=LlmRunRepository(session).start(project_id=project,llm_provider='internal' if det else 'gemini',
        llm_model='deterministic_metric_answer' if det else 'gemini-3.5-flash-lite',prompt_name='test',prompt_version='1',
        operation_type=op or ('deterministic_metric_answer' if det else 'rag_assistant_generation'),execution_mode='runtime',
        provider_invocation_count=(0 if det else 1) if known_invocation else None)
    LlmRunRepository(session).complete(run.id,usage=TokenUsage(0,0,0) if det else usage(),llm_latency_ms=0 if det else latency,
        end_to_end_latency_ms=100 if det else latency+500)
    CostRepository(session).record(llm_run_id=run.id,project_id=project,llm_provider=run.llm_provider,llm_model=run.llm_model,
        usage=TokenUsage(0,0,0) if det else usage(),estimated_cost_usd=Decimal(0) if det else cost,
        estimate_details=price(deterministic=det) if det or (cost is not None and known_invocation) else None)
    return run


@pytest.mark.parametrize('costs,dets,status,subtotal',[
    ([],0,'not_measured',None),([],1,'complete',Decimal(0)),([None],0,'unavailable',None),([None],1,'unavailable',None),
    ([Decimal('.0044059')],0,'complete',Decimal('.0044059')),
    ([Decimal('.0044059'),None],0,'partial',Decimal('.0044059')),
    ([Decimal('.0044059'),Decimal('.0044059')],0,'complete',Decimal('.0088118')),
])
def test_operation_observability_sql_unknown_zero_partial_totals(db_session,costs,dets,status,subtotal):
    project=_create_project(db_session)
    for cost in costs:record(db_session,project,cost=cost)
    for _ in range(dets):record(db_session,project,det=True)
    result=CostRepository(db_session).summary(project_id=project)
    assert result['cost_status']==status and result['priced_subtotal_usd']==subtotal
    assert result['model_invocations']==len(costs) and result['total_operations']==len(costs)+dets
    assert result['unpriced_inference_events']==sum(c is None for c in costs)
    if any(c is None for c in costs):assert result['estimated_cost_usd'] is None


def test_operation_observability_latency_population_excludes_deterministic_zero(db_session):
    project=_create_project(db_session)
    record(db_session,project);record(db_session,project,det=True)
    result=operation_analytics(db_session,project)
    assert result['latencies']['gemini_inference']==dict(samples=1,mean_ms=9320,p50_ms=9320,p95_ms=9320)
    assert result['latencies']['end_to_end']['samples']==2
    record(db_session,project,latency=1000,op='semantic_feature_extraction')
    assert operation_analytics(db_session,project)['latencies']['gemini_inference']['mean_ms']==5160
    assert operation_analytics(db_session,project)['latencies']['semantic_inference']['samples']==1


def test_operation_observability_no_sample_percentiles_and_legacy_exclusion(db_session):
    assert distribution([])==dict(samples=0,mean_ms=None,p50_ms=None,p95_ms=None)
    assert distribution([0,100])==dict(samples=2,mean_ms=50,p50_ms=50,p95_ms=95)
    project=_create_project(db_session);record(db_session,project,known_invocation=False)
    result=operation_analytics(db_session,project)
    assert result['latencies']['gemini_inference']['samples']==0 and result['legacy_latency_excluded']==1


def test_operation_observability_cost_idempotency_preserves_first_event(db_session):
    project=_create_project(db_session)
    run=record(db_session,project)
    repo=CostRepository(db_session)
    args=dict(llm_run_id=run.id,project_id=project,llm_provider='gemini',llm_model=run.llm_model,usage=usage(),
        estimated_cost_usd=Decimal('.0044059'),estimate_details=price(),event_key=run.id+':inference')
    first=repo.record(**args);second=repo.record(**{**args,'estimated_cost_usd':None})
    assert first.id==second.id and second.estimated_cost_usd==Decimal('.0044059')


def test_operation_observability_failed_attempts_with_and_without_usage(db_session):
    project=_create_project(db_session);run=record(db_session,project,cost=Decimal('.0044059'))
    LlmRunRepository(db_session).fail(run.id,error_code='MALFORMED_JSON',usage=usage(),llm_latency_ms=9320)
    unknown=record(db_session,project)
    LlmRunRepository(db_session).fail(unknown.id,error_code='TIMEOUT',usage=TokenUsage(),llm_latency_ms=500)
    assert operation_analytics(db_session,project)['latencies']['gemini_inference']['samples']==2
    assert CostRepository(db_session).summary(project_id=project)['cost_status']=='partial'


@pytest.mark.parametrize('damage', ['malformed','timeout','ready','deduplicated'])
def test_operation_observability_semantic_actual_call_failure_and_cache_boundaries(monkeypatch,damage):
    from app.services import semantic_service as service
    from app.evaluations.intelligence_fixtures import fixtures,subject
    import json
    a=subject('content_1',fixtures()['educational'],semantic=True)
    ctx,payload=a[2],a[3];calls=[];events=[];annotations=[]
    row=dict(project_id=ctx['project_id'],content_id=ctx['content_id'],slot=ctx['slot'],model_id='gemini-3.5-flash-lite',
        prompt_version='1.0.0',attempts=1,context=ctx)
    monkeypatch.setattr(service.store,'claim_snapshot',lambda key:damage!='deduplicated')
    monkeypatch.setattr(service.store,'read_snapshot',lambda key:row)
    monkeypatch.setattr(service.store,'transition',lambda *a,**kw:True)
    monkeypatch.setattr(service,'semantic_identity',lambda *a:('synthetic-snapshot',ctx,{'system_prompt':'Synthetic feature extraction'}))
    monkeypatch.setattr(service,'start_llm_run',lambda **kw:'synthetic-run')
    monkeypatch.setattr(service,'complete_llm_run',lambda *a,**kw:True)
    monkeypatch.setattr(service,'fail_llm_run',lambda *a,**kw:True)
    monkeypatch.setattr(service,'record_cost_event',lambda **kw:events.append(kw))
    monkeypatch.setattr(service,'annotate_operation',lambda *a,**kw:annotations.append(kw))
    class Model:
        async def ainvoke(self,*a,**kw):
            calls.append(1)
            if damage=='timeout':raise TimeoutError('Synthetic timeout')
            return SimpleNamespace(content='not json' if damage=='malformed' else json.dumps(payload),usage_metadata={
                'input_tokens':10,'output_tokens':2,'total_tokens':12,'input_token_details':{'cache_read':0}})
    monkeypatch.setattr(service,'get_llm',lambda **kw:Model())
    result=service.process_semantic_snapshot('synthetic-snapshot')
    if damage=='deduplicated':
        assert not calls and not events and not annotations
    else:
        assert len(calls)==len(events)==1 and events[0]['provider_invocation_count']==1
        assert annotations[0]['provider_invocation_count']==1
        if damage=='timeout':assert events[0]['usage'] is None
        else:assert events[0]['usage'].total_tokens==12
        assert result['status']==('ready' if damage=='ready' else 'failed')


def test_operation_observability_storage_failure_does_not_escape(monkeypatch):
    from app.services import llm_observability_service as service
    from contextlib import contextmanager
    monkeypatch.setattr(service,'is_database_configured',lambda:True)
    @contextmanager
    def broken():raise RuntimeError('Synthetic telemetry storage failure');yield
    monkeypatch.setattr(service,'database_session',broken)
    assert service.record_cost_event(llm_run_id='synthetic',project_id='synthetic',llm_provider='gemini',
        llm_model='unknown',usage=TokenUsage(),provider_invocation_count=1) is False


def test_operation_observability_historical_unknown_duplicate_event_is_not_dropped(db_session):
    project=_create_project(db_session);run=record(db_session,project,cost=Decimal('.0044059'),known_invocation=False)
    CostRepository(db_session).record(llm_run_id=run.id,project_id=project,llm_provider='gemini',llm_model=run.llm_model,
        usage=None,estimated_cost_usd=None)
    summary=CostRepository(db_session).summary(project_id=project)
    assert summary['event_count']==2 and summary['inference_events']==2
    assert summary['unpriced_inference_events']==1 and summary['cost_status']=='partial'


def test_operation_observability_partial_component_subtotal_is_not_complete(db_session):
    project=_create_project(db_session);run=record(db_session,project)
    repo=CostRepository(db_session)
    partial=price(parse_token_usage({'usage_metadata':{'input_tokens':100,'input_token_details':{'cache_read':0}}}))
    repo.record(llm_run_id=run.id,project_id=project,llm_provider='gemini',llm_model=run.llm_model,usage=TokenUsage(100),
        estimated_cost_usd=None,estimate_details=partial,event_key=run.id+':partial')
    result=repo.summary(project_id=project)
    assert result['estimated_cost_usd'] is None and result['cost_status']=='partial'
    assert result['priced_subtotal_usd']==Decimal('.00003')



def test_operation_observability_unknown_native_output_does_not_invent_thinking_or_tool_charges():
    value=parse_token_usage({'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':30,'totalTokenCount':140}})
    assert value.output_tokens is None and value.thinking_tokens is None and value.candidate_tokens==30
    assert price(value)['estimated_cost_usd'] is None


def test_operation_observability_native_attribute_usage_shape():
    value=parse_token_usage(SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=100,candidates_token_count=20,
        thoughts_token_count=5,cached_content_token_count=0,total_token_count=125)))
    assert value.output_tokens==25 and value.completeness=='complete'



def test_operation_observability_historical_known_money_is_not_verified_pricing(db_session):
    project=_create_project(db_session);record(db_session,project,cost=Decimal('.0044059'),known_invocation=False)
    summary=CostRepository(db_session).summary(project_id=project)
    assert summary['estimated_cost_usd']==Decimal('.0044059')
    assert summary['cost_status']=='legacy_unverified' and summary['legacy_estimate_events']==1
    assert summary['verified_pricing_coverage']==0
    assert operation_analytics(db_session,project)['daily'][0]['cost_status']=='legacy_unverified'



def test_operation_observability_offline_evaluation_markers_never_enter_runtime_billing(db_session):
    project=_create_project(db_session);run=record(db_session,project,cost=Decimal('.0044059'))
    run.execution_mode='mocked_model_evaluation'
    db_session.flush()
    summary=CostRepository(db_session).summary(project_id=project)
    assert summary['total_operations']==0 and summary['model_invocations']==0 and summary['event_count']==0
    analytics=operation_analytics(db_session,project)
    assert analytics['excluded_evaluation_operations']==1 and analytics['latencies']['gemini_inference']['samples']==0



@pytest.mark.parametrize('mode',['ready','empty','timeout'])
def test_operation_observability_existing_diagnostic_is_tracked_without_fake_project(monkeypatch,mode):
    import asyncio
    from app.services.llm_service import _tracked_diagnostic_invoke
    from app.services import llm_observability_service as service
    starts=[];events=[];failed=[]
    monkeypatch.setattr(service,'start_llm_run',lambda **kw:starts.append(kw) or 'diagnostic')
    monkeypatch.setattr(service,'complete_llm_run',lambda *a,**kw:True)
    monkeypatch.setattr(service,'fail_llm_run',lambda *a,**kw:failed.append(kw))
    monkeypatch.setattr(service,'record_cost_event',lambda **kw:events.append(kw))
    monkeypatch.setattr(service,'annotate_operation',lambda *a,**kw:True)
    class Model:
        async def ainvoke(self,prompt):
            if mode=='timeout':raise TimeoutError('Synthetic diagnostic timeout')
            return SimpleNamespace(content='Ready' if mode=='ready' else '',usage_metadata={'input_tokens':10,'output_tokens':2,'total_tokens':12})
    if mode=='ready':asyncio.run(_tracked_diagnostic_invoke(Model(),'Synthetic prompt','fixture-model'))
    else:
        with pytest.raises((ValueError,TimeoutError)):asyncio.run(_tracked_diagnostic_invoke(Model(),'Synthetic prompt','fixture-model'))
    assert starts[0]['project_id'] is None and starts[0]['operation_type']=='diagnostic_generation'
    assert len(events)==1 and events[0]['provider_invocation_count']==1
    assert bool(failed)==(mode!='ready')
    if mode!='timeout':assert events[0]['usage'].total_tokens==12


def test_operation_observability_projectless_diagnostic_has_global_scope_only(db_session):
    run=LlmRunRepository(db_session).start(project_id=None,llm_provider='gemini',llm_model='fixture-model',
        prompt_name='diagnostic_generation',prompt_version='1',operation_type='diagnostic_generation',execution_mode='runtime',provider_invocation_count=1)
    CostRepository(db_session).record(llm_run_id=run.id,project_id=None,llm_provider='gemini',llm_model='fixture-model',usage=None,estimated_cost_usd=None)
    assert CostRepository(db_session).summary()['model_invocations']==1
    assert CostRepository(db_session).summary(project_id='unrelated')['total_operations']==0



def test_operation_observability_optional_native_none_is_unavailable_not_invalid():
    value=parse_token_usage({'usage_metadata':{'prompt_token_count':100,'candidates_token_count':20,
        'thoughts_token_count':None,'cached_content_token_count':None,'tool_use_prompt_token_count':None,'total_token_count':120}})
    assert value.output_tokens==20 and value.thinking_tokens is None and value.cached_input_tokens is None
    assert not value.warnings and price(value)['status']=='partial'


def test_operation_observability_tier_can_be_reported_outside_usage_counts():
    value=parse_token_usage({'usage_metadata':{'input_tokens':100,'output_tokens':20,'total_tokens':120,'input_token_details':{'cache_read':0}},
        'response_metadata':{'serviceTier':'standard','model_name':'gemini-3.5-flash-lite'}})
    assert value.service_tier=='standard' and value.model_id=='gemini-3.5-flash-lite'
