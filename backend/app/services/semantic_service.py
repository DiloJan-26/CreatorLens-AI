"""Explicit queued semantic extraction; GET paths only read compatible snapshots."""
import asyncio
from contextvars import ContextVar
from app.services.llm_observability_service import annotate_operation
from dataclasses import asdict
from datetime import datetime, UTC
import json
from pathlib import Path
from time import perf_counter
import yaml
from app.core.config import get_settings
from app.core.model_policy import model_configuration_error
from app.db.repositories import semantic_repository as store
from app.insights.semantic_models import CreativeFeatures, PROMPT_VERSION, SCHEMA_VERSION, CREATIVE_POLICY
from app.insights.semantic_evidence import build_semantic_input, parse_features
from app.services.hash_service import hash_payload
from app.services.storage_compat_service import get_project_detail_record, get_transcript_segments
from app.services.llm_service import get_llm, _message_text
from app.llm.token_usage import parse_token_usage
from app.llm.tracing import OptionalTrace
from app.services.llm_observability_service import start_llm_run, complete_llm_run, fail_llm_run, record_cost_event

PROMPT_PATH = Path(__file__).resolve().parents[1] / 'llm/prompts/semantic/creative_features.yaml'
OPERATION = 'semantic_feature_extraction'
_INVOCATION = ContextVar('semantic_invocation',default=None)


def semantic_identity(project_id, slot):
    error=model_configuration_error(get_settings())
    if error:raise ValueError(error)
    if slot not in {'content_1','content_2'}:
        raise ValueError('Invalid content slot.')
    project = get_project_detail_record(project_id)
    if project is None:
        raise LookupError('Project not found.')
    item = next((x for x in project.get('content_items',[]) if x.get('slot') == slot), None)
    if item is None:
        raise LookupError('Content not found.')
    segments = get_transcript_segments(project_id=project_id, platform=item['platform'], slot=slot)
    context = build_semantic_input(project_id, item, segments, supported_languages=tuple(x.strip().lower() for x in get_settings().semantic_supported_languages.split(",") if x.strip()))
    prompt = yaml.safe_load(PROMPT_PATH.read_text(encoding='utf-8'))
    if prompt['version'] != PROMPT_VERSION or prompt['name'] != OPERATION:
        raise ValueError('Semantic prompt identity mismatch.')
    settings = get_settings()
    key = hash_payload(dict(input_revision=context['input_revision'], model=settings.llm_model,
        provider=settings.llm_provider, prompt=prompt, schema=CreativeFeatures.model_json_schema(), creative_policy=CREATIVE_POLICY))
    return key, context, prompt


def get_semantic_analysis(project_id, slot):
    key, context, _ = semantic_identity(project_id, slot)
    row = store.read_snapshot(key)
    if row is None:
        return dict(status='unavailable', snapshot_id=None, input_revision=context['input_revision'],
            cache_hit=False, reason='No compatible semantic snapshot. Explicit queue request required.')
    result = row['result'] if row['status'] == 'ready' else None
    # Validate persisted evidence again; storage is not a substitute for ownership checks.
    if result:
        parse_features(json.dumps(result), context)
    return dict(status='pending' if row['status'] == 'running' else row['status'], snapshot_id=key,
        input_revision=context['input_revision'], features=result, model_id=row['model_id'], prompt_version=row['prompt_version'],
        schema_version=row['schema_version'], creative_policy=CREATIVE_POLICY, processing=row['processing'],
        attempts=row['attempts'], cache_hit=row['status'] == 'ready', error_code=row['error_code'],
        limitations=context['limitations'], evidence_sources=context['sources'], evidence_complete=context['complete'],
        assessments=[dict(feature=f['feature'], value=f['value'], status=f['status'],
            explanation=f"{f['feature']}: {f['value']}. Model-derived textual interpretation; inspect cited sources.",
            limitations=context['limitations'], evidence=f['evidence']) for f in result['features']] if result else [])


def queue_semantic_analysis(project_id, slot, *, retry_failed=False, recover_stale=False):
    key, context, _ = semantic_identity(project_id, slot)
    row = store.read_snapshot(key)
    created = False
    if row is None:
        created = store.create_pending(key=key, context=context, model_id=get_settings().llm_model,
            prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION)
        row = store.read_snapshot(key)
    if not context['content_id'] or not any(s['source_type'] == 'transcript' for s in context['sources']):
        store.transition(key, 'pending', 'unavailable', error_code='EVIDENCE_UNAVAILABLE')
        return get_semantic_analysis(project_id, slot)
    if recover_stale and row['status'] == 'running':
        timestamp = row['updated_at']
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        if (datetime.now(UTC)-timestamp).total_seconds() >= 300:
            store.transition(key, 'running', 'failed', error_code='WORKER_INTERRUPTED')
            row = store.read_snapshot(key)
    if retry_failed and row['status'] == 'failed' and row['attempts'] < 2:
        created = store.transition(key, 'failed', 'pending', error_code=None)
    # pending requests may safely republish lost messages: atomic worker claim deduplicates.
    if created or row['status'] == 'pending':
        try:
            from app.workers.semantic_tasks import extract_semantic_features
            extract_semantic_features.apply_async(args=[key], task_id=key)
        except Exception:
            store.transition(key, 'pending', 'failed', error_code='QUEUE_UNAVAILABLE')
    return get_semantic_analysis(project_id, slot)


async def _invoke(context, prompt):
    llm = get_llm(streaming=False, temperature=0, max_output_tokens=4096, max_retries=0, timeout=60)
    messages = [('system', prompt['system_prompt']), ('human', json.dumps({'schema': CreativeFeatures.model_json_schema(), 'input':context}, ensure_ascii=False))]
    state=_INVOCATION.get()
    if state is not None: state.update(count=1,started=perf_counter(),inference_at=datetime.now(UTC))
    return await asyncio.wait_for(llm.ainvoke(messages, response_mime_type="application/json", response_schema=CreativeFeatures.model_json_schema()), timeout=65)


def process_semantic_snapshot(key):
    if not store.claim_snapshot(key):
        return {'status':'deduplicated'}
    row = store.read_snapshot(key)
    context = row['context']
    run_id = None
    usage = None
    start = perf_counter()
    state={"count":0}; token=_INVOCATION.set(state)
    cost_recorded=False
    invocation_ms=None
    processing = dict(operation_type=OPERATION, cache_hit=False, actual_inference=False,
        model_id=row['model_id'], prompt_version=row['prompt_version'], content_id=row['content_id'], slot=row['slot'])
    try:
        current_key, current_context, prompt = semantic_identity(row['project_id'], row['slot'])
        if current_key != key:
            raise ValueError('STALE_INPUT')
        run_id = start_llm_run(project_id=row['project_id'], llm_provider='gemini', llm_model=row['model_id'],
            prompt_name=OPERATION, prompt_version=PROMPT_VERSION,operation_type=OPERATION,execution_mode="runtime",provider_invocation_count=0,
            telemetry={"content_id":row["content_id"],"slot":row["slot"],"snapshot_id":key,"operation_version":"1.0.0","policy_versions":{"creative":CREATIVE_POLICY,"schema":SCHEMA_VERSION,"prompt":PROMPT_VERSION}})
        with OptionalTrace('creatorlens.semantic_features', run_type='llm', inputs={'snapshot_id':key},
            metadata={'operation_type':OPERATION,'project_id':row['project_id'],'content_id':row['content_id'],
                      'prompt_version':PROMPT_VERSION,'model':row['model_id']}) as span:
            processing.update(actual_inference=None, provider_invocation_status='attempted')
            try:
                response = asyncio.run(_invoke(context, prompt))
            finally:
                if state.get('started') is not None: invocation_ms=round((perf_counter()-state['started'])*1000)
            state['count']=1
            processing.update(actual_inference=True, provider_invocation_status='response_received')
            usage = parse_token_usage(response)
            processing['token_usage'] = asdict(usage)
            # Persist tokens/cost even when schema or evidence validation subsequently fails.
            record_cost_event(llm_run_id=run_id, project_id=row['project_id'], llm_provider='gemini',
                llm_model=row['model_id'], usage=usage,
                estimated_cost_usd=None,
                pricing_source=None,provider_invocation_count=state['count'],inference_at=state.get('inference_at'))
            cost_recorded=True
            processing.update(requested_model=row['model_id'],observed_model=usage.model_id,
                model_identity_status='reported' if usage.model_id else 'unreported')
            if usage.model_id is not None and usage.model_id!=row['model_id']:
                raise ValueError('SEMANTIC_MODEL_MISMATCH')
            features = parse_features(_message_text(response), context)
            if semantic_identity(row['project_id'], row['slot'])[0] != key:
                raise ValueError('STALE_INPUT')
            processing.update(latency_ms=round((perf_counter()-start)*1000), provider_status='completed', langsmith_trace_id=span.trace_id)
            if not store.transition(key,'running','ready', attempt=row['attempts'], result=features.model_dump(mode='json'), processing=processing, error_code=None):
                raise ValueError('STALE_INPUT')
            complete_llm_run(run_id, usage=usage, provider_invocation_count=state["count"],llm_latency_ms=invocation_ms, cache_hit=False, cache_miss=True, langsmith_trace_id=span.trace_id)
            span.set_outputs({'snapshot_id':key,'status':'ready'})
        return {'status':'ready'}
    except Exception as exc:
        code = ('STALE_INPUT' if str(exc) == 'STALE_INPUT' else
            'SEMANTIC_TIMEOUT' if isinstance(exc, TimeoutError) else
            'SEMANTIC_RATE_LIMIT' if getattr(exc, 'status_code', None) == 429 or type(exc).__name__ in {'ResourceExhausted','TooManyRequests'} else
            'SEMANTIC_MODEL_MISMATCH' if str(exc)=='SEMANTIC_MODEL_MISMATCH' else
            'SEMANTIC_VALIDATION_FAILED' if isinstance(exc, ValueError) else 'SEMANTIC_EXTRACTION_FAILED')
        processing.update(latency_ms=round((perf_counter()-start)*1000), provider_status='failed', exception_type=type(exc).__name__)
        store.transition(key,'running','failed', attempt=row['attempts'], error_code=code, processing=processing)
        fail_llm_run(run_id, error_code=code, usage=usage, provider_invocation_count=state["count"],llm_latency_ms=invocation_ms)
        return {'status':'failed','error_code':code}

    finally:
        if run_id is not None:
            annotate_operation(run_id,usage=usage,provider_invocation_count=state['count'],
                end_to_end_latency_ms=round((perf_counter()-start)*1000))
            if not cost_recorded:
                record_cost_event(llm_run_id=run_id,project_id=row['project_id'],llm_provider='gemini',
                    llm_model=row['model_id'],usage=usage,provider_invocation_count=state['count'],inference_at=state.get('inference_at'))
        _INVOCATION.reset(token)
