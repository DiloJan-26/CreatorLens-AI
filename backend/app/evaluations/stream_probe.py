"""Mocked SSE integration probe. Executed only in an isolated evaluation subprocess."""
import asyncio
from contextlib import ExitStack
import json
from types import SimpleNamespace
from unittest.mock import patch
from app.evaluations.intelligence_fixtures import fixtures,assistant_context,PROJECT
from app.models.chat import ChatMessage,ChatSession,ChatStreamRequest,RagContext
from app.rag import chat_service


def evaluate_stream(mode):
    question='Why is this hook clearer?' if mode=='timeout' else 'How many views does Content 1 have?'
    context,citations,question=assistant_context(fixtures()['educational'],dict(question=question))
    messages=[];events=[];calls=[];cost=[];failures=[]
    def add(**kwargs):
        messages.append(kwargs)
        return ChatMessage(message_id='message-'+str(len(messages)),project_id=PROJECT,session_id='synthetic-session',role=kwargs['role'],content=kwargs['content'],created_at='2026-01-01')
    class MockModel:
        async def ainvoke(self,*args):calls.append('mocked_provider');raise TimeoutError('Synthetic timeout')
    def get_llm(**kwargs):
        if mode!='timeout':raise AssertionError('Avoidable inference in deterministic stream.')
        return MockModel()
    with ExitStack() as stack:
        replacements=dict(create_or_get_session=lambda **kwargs:ChatSession(session_id='synthetic-session',project_id=PROJECT,created_at='2026-01-01',updated_at='2026-01-01'),add_message=add,get_recent_messages=lambda **kwargs:[],build_rag_context=lambda **kwargs:RagContext(project_id=PROJECT,intent='hook_analysis' if mode=='timeout' else 'metrics',intelligence=context,structured_context='Synthetic canonical context',retrieved_context='',citations=citations),get_llm=get_llm,get_project_runtime_signals=lambda project:SimpleNamespace(cache_hit=None,cache_miss=None,transcript_provider=None,transcript_fallback_used=None,embedding_reused=None),start_llm_run=lambda **kwargs:None,complete_llm_run=lambda *args,**kwargs:False,fail_llm_run=lambda *args,**kwargs:failures.append(kwargs),record_cost_event=lambda **kwargs:cost.append(kwargs),save_chat_citations=lambda **kwargs:None)
        for name,value in replacements.items():stack.enter_context(patch.object(chat_service,name,value))
        stack.enter_context(patch('app.rag.intelligence_context.context_is_current',return_value=True))
        async def collect():return [event async for event in chat_service.stream_chat_answer(PROJECT,ChatStreamRequest(message=question))]
        for event in asyncio.run(collect()):
            lines=event.strip().splitlines();events.append((lines[0].removeprefix('event: ').strip(),json.loads(lines[1].removeprefix('data: '))))
    return dict(structured_count=sum(n=='structured_answer' for n,d in events),done_count=sum(n=='done' for n,d in events),error_count=sum(n=='error' for n,d in events),assistant_messages=sum(m['role']=='assistant' for m in messages),provider_calls=len(calls),history_association=all(m['project_id']==PROJECT and m['session_id']=='synthetic-session' for m in messages),provider_failure_recorded=any(f['error_code']=='ASSISTANT_PROVIDER_FAILURE' for f in failures),deterministic_tokens=cost[0]['usage'].total_tokens if cost else None)
