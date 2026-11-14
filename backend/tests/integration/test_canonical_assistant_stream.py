"""Exercise canonical SSE, memory and telemetry with zero live provider access."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from app.rag import chat_service,context_builder,intelligence_context
from app.models.chat import ChatStreamRequest,ChatMessage,ChatSession
from app.models.rag import RetrieveResponse
from app.services import storage_compat_service
from tests.unit.test_assistant_intelligence import configure,semantic,PROJECT


def decode(event):
    lines=event.strip().splitlines()
    return lines[0].removeprefix('event: ').strip(),json.loads(lines[1].removeprefix('data: '))


@pytest.mark.parametrize('mode',['deterministic','generated','malformed','timeout','changed'])
def test_sse_preserves_canonical_answer_and_tracks_real_execution(monkeypatch,mode):
    project=configure(monkeypatch,semantic('content_1',{'verbal_hook_clarity':'partial'}),semantic('content_2'))
    monkeypatch.setattr(context_builder,'retrieve_project_chunks',lambda **kwargs:RetrieveResponse(project_id=PROJECT,query='Explain the opening',total_results=0,results=[]))
    monkeypatch.setattr(storage_compat_service,'get_rag_chunks',lambda project_id:[])
    question='Who wins under Reach?' if mode=='deterministic' else 'Why is this hook clearer?'
    expected_context=intelligence_context.build_intelligence_context(PROJECT,question,'reach')
    expected=intelligence_context.canonical_answer(expected_context,question,'performance_reasoning' if mode=='deterministic' else 'hook_analysis')
    counts={'admissions':0,'invoke':0,'provider':[],'complete':[],'failed':[],'cost':[],'messages':[],'citations':[]}
    from app.services import provider_admission
    def admit(*args,**kwargs):
        counts['admissions']+=1
        return None  # Synthetic generation only; no real quota/database admission.
    monkeypatch.setattr(provider_admission,'admit_current',admit)
    monkeypatch.setattr(chat_service,'create_or_get_session',lambda **kwargs:ChatSession(session_id='session',project_id=PROJECT,created_at='now',updated_at='now'))
    def add(**kwargs):
        counts['messages'].append(kwargs)
        return ChatMessage(message_id='message-'+str(len(counts['messages'])),session_id='session',project_id=PROJECT,role=kwargs['role'],content=kwargs['content'],created_at='now')
    monkeypatch.setattr(chat_service,'add_message',add)
    monkeypatch.setattr(chat_service,'get_recent_messages',lambda **kwargs:[])
    monkeypatch.setattr(chat_service,'get_project_runtime_signals',lambda project_id:SimpleNamespace(cache_hit=None,cache_miss=None,transcript_provider=None,transcript_fallback_used=None,embedding_reused=None))
    monkeypatch.setattr(chat_service,'start_llm_run',lambda **kwargs:counts['provider'].append(kwargs) or 'run')
    monkeypatch.setattr(chat_service,'complete_llm_run',lambda *args,**kwargs:counts['complete'].append(kwargs))
    def fail(run_id,*,error_code,usage=None,retrieval_latency_ms=None,llm_latency_ms=None,langsmith_trace_id=None,provider_invocation_count=None):
        counts['failed'].append(dict(error_code=error_code,usage=usage,provider_invocation_count=provider_invocation_count,retrieval_latency_ms=retrieval_latency_ms,llm_latency_ms=llm_latency_ms,langsmith_trace_id=langsmith_trace_id))
    monkeypatch.setattr(chat_service,'fail_llm_run',fail)
    monkeypatch.setattr(chat_service,'record_cost_event',lambda **kwargs:counts['cost'].append(kwargs))
    monkeypatch.setattr(chat_service,'save_chat_citations',lambda **kwargs:counts['citations'].extend(kwargs['citations']))
    class MockLlm:
        async def ainvoke(self,messages):
            counts['invoke']+=1
            assert 'untrusted data' in messages[0].content
            if mode=='timeout':raise TimeoutError('Synthetic timeout')
            if mode=='changed':project['content_items'][0]['views']=999999
            payload=expected.model_dump(mode='json')
            if mode=='generated':payload['key_reasons']=['The cited spoken passage introduces the topic.']
            return SimpleNamespace(content='bad json' if mode=='malformed' else json.dumps(payload),usage_metadata={'input_tokens':100,'output_tokens':25,'total_tokens':125})
    def llm(**kwargs):
        if mode=='deterministic':raise AssertionError('Deterministic answers must bypass Gemini.')
        assert kwargs['max_retries']==0 and kwargs['timeout']==30
        return MockLlm()
    monkeypatch.setattr(chat_service,'get_llm',llm)
    async def collect():return [decode(event) async for event in chat_service.stream_chat_answer(PROJECT,ChatStreamRequest(message=question,objective='reach'))]
    events=asyncio.run(collect())
    assert not any(name=='error' for name,data in events)
    structured=[data for name,data in events if name=='structured_answer']
    assert len(structured)==1
    if mode=='changed':assert structured[0]['answer']['evidence_status']=='evidence_changed'
    else:assert structured[0]['answer']['winner']==expected.winner
    assert structured[0]['answer']['objective']==expected.objective
    assert len(counts['messages'])==2 and counts['messages'][1]['role']=='assistant'
    assert sum(name=='done' for name,data in events)==1 and sum(name=='citations' for name,data in events)==1
    assert bool(counts['citations'])==(mode!='changed')
    assert 'Confidence:' not in counts['messages'][1]['content']
    if mode=='deterministic':
        assert counts['admissions']==0
        assert counts['invoke']==0 and counts['provider'][0]['llm_provider']=='internal'
        assert counts['cost'][0]['usage'].total_tokens==0
    else:
        assert counts['admissions']==1
        assert 'provider_operation_id' in counts['provider'][0]['telemetry']
        assert counts['invoke']==1 and counts['provider'][0]['llm_provider']=='gemini'
        if mode=='timeout':
            assert counts['failed'][0]['error_code']=='ASSISTANT_PROVIDER_FAILURE'
            assert counts['failed'][0]['provider_invocation_count']==1
            assert counts['cost'][0]['usage'].total_tokens is None
        else:assert counts['cost'][0]['usage'].total_tokens==125
    assert len(counts['cost'])==1
    assert counts['cost'][0]['provider_invocation_count']==(0 if mode=='deterministic' else 1)
    if mode in {'malformed','timeout'}:assert structured[0]['fallback_used'] and structured[0]['warnings']


@pytest.mark.parametrize('question,selected,expected',[
    ('How many likes does Content 1 have?','engagement','engagement'),
    ('Which has more views?','engagement','reach'),
])
def test_context_preview_preserves_request_objective_without_inference(monkeypatch,question,selected,expected):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.chat import router
    configure(monkeypatch)
    app=FastAPI();app.include_router(router)
    with TestClient(app) as client:
        response=client.post(f'/api/projects/{PROJECT}/chat/context-preview',json={'message':question,'objective':selected})
        assert response.status_code==200
        assert response.json()['intelligence']['selected_objective']==expected
        assert client.post(f'/api/projects/{PROJECT}/chat/stream',json={'message':question,'objective':'virality'}).status_code==422
