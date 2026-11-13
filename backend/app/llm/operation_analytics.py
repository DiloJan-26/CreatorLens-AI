"""Whole-scope timing populations; no history pagination or deterministic-zero dilution."""
from collections import defaultdict
import math
from sqlalchemy import select, func, case, or_
from app.db.models.llm_observability import LlmRun, CostEvent


def distribution(values):
    values=sorted(v for v in values if v is not None)
    def percentile(p):
        if not values:return None
        x=(len(values)-1)*p;lo=math.floor(x);hi=math.ceil(x)
        return values[lo]+(values[hi]-values[lo])*(x-lo)
    return dict(samples=len(values),mean_ms=sum(values)/len(values) if values else None,p50_ms=percentile(.5),p95_ms=percentile(.95))


def operation_analytics(session,project_id=None):
    query=select(LlmRun.operation_type,LlmRun.execution_mode,LlmRun.provider_invocation_count,LlmRun.llm_provider,
        LlmRun.llm_model,LlmRun.llm_latency_ms,LlmRun.retrieval_latency_ms,LlmRun.end_to_end_latency_ms,
        LlmRun.deterministic_latency_ms,LlmRun.context_latency_ms,LlmRun.status,LlmRun.created_at)
    if project_id is not None:query=query.where(LlmRun.project_id==project_id)
    buckets=defaultdict(list);operations=defaultdict(int);days=defaultdict(lambda:dict(operations=0,model_invocations=0));legacy=0;excluded=0
    for op,mode,count,provider,model,inference,retrieval,end,det,context,status,created in session.execute(query):
        if mode not in {None,'runtime'}:
            excluded+=1;continue
        operations[op or 'legacy_unclassified']+=1
        day=days[created.date().isoformat()];day['operations']+=1;day['model_invocations']+=count or 0
        if count is None:legacy+=1
        if count==1 and provider=='gemini' and inference is not None:
            buckets['gemini_inference'].append(inference)
            if op=='semantic_feature_extraction':buckets['semantic_inference'].append(inference)
        if retrieval is not None:buckets['retrieval'].append(retrieval)
        if end is not None:buckets['end_to_end'].append(end)
        if det is not None:buckets['deterministic_processing'].append(det)
        if context is not None:buckets['context_preparation'].append(context)
    is_inference=CostEvent.llm_provider!='internal'
    costs=select(func.date(CostEvent.created_at),func.sum(CostEvent.input_tokens),func.sum(CostEvent.output_tokens),
        func.sum(case((is_inference,func.coalesce(CostEvent.priced_subtotal_usd,CostEvent.estimated_cost_usd)),else_=None)),
        func.sum(case((is_inference & CostEvent.estimated_cost_usd.is_(None),1),else_=0)),
        func.sum(case((is_inference & CostEvent.estimated_cost_usd.is_not(None),1),else_=0)),
        func.sum(case((is_inference & CostEvent.estimated_cost_usd.is_not(None) & CostEvent.cost_status.is_(None),1),else_=0)))
    costs=costs.join(LlmRun,CostEvent.llm_run_id==LlmRun.id).where(or_(LlmRun.execution_mode.is_(None),LlmRun.execution_mode=='runtime')).group_by(func.date(CostEvent.created_at))
    if project_id is not None:costs=costs.where(CostEvent.project_id==project_id)
    for day,inputs,outputs,cost,unknown,known,unverified in session.execute(costs):
        status='partial' if unknown and cost is not None else 'unavailable' if unknown else 'complete'
        if status=='complete' and unverified:status='legacy_unverified'
        days[str(day)].update(legacy_estimate_events=int(unverified or 0),input_tokens=inputs,output_tokens=outputs,priced_subtotal_usd=str(cost) if cost is not None else ('0' if not unknown else None),
            cost_status=status,priced_inference_events=int(known or 0),unpriced_inference_events=int(unknown or 0))
    names=('gemini_inference','semantic_inference','retrieval','end_to_end','deterministic_processing','context_preparation')
    return dict(latencies={k:distribution(buckets[k]) for k in names},operations=dict(operations),daily=[dict(date=k,**v) for k,v in sorted(days.items())],
        excluded_evaluation_operations=excluded,legacy_latency_excluded=legacy,latency_policy='Single-invocation runtime attempts with known duration, including failed attempts; legacy unknown invocation counts excluded. End-to-end is server request processing, not time-to-first-token.')
