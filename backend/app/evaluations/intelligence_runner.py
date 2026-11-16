"""Versioned extension of the existing evaluation runner/repository, offline by default."""
import json
import math
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,UTC
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from app.evaluations.intelligence_models import IntelligenceCase,DATASETS,DATASET_VERSION,EVALUATOR
from app.evaluations.intelligence_fixtures import fixtures,ROOT
from app.evaluations.intelligence_checks import execute_case
from app.evaluations.fixture_loader import EvaluationFixtureError
from app.schemas.evaluation import EvaluationCaseReport,EvaluationRunReport,EvaluationCheckResult,EvaluationCaseDefinition,EvaluationRubric

_ACTIVE=ContextVar('intelligence_evaluation_offline',default=False)
_INSTALLED=False


@contextmanager
def offline_boundary():
    global _INSTALLED
    if not _INSTALLED:
        def guard(event,args):
            if _ACTIVE.get() and (event=='socket.connect' or event=='socket.getaddrinfo'):
                address=args[1] if event=='socket.connect' else args[0]
                host=address[0] if isinstance(address,tuple) else address
                if host not in {'127.0.0.1','::1','localhost',None}:raise RuntimeError('Offline evaluation blocked external network access.')
        sys.addaudithook(guard);_INSTALLED=True
    token=_ACTIVE.set(True)
    try:yield
    finally:_ACTIVE.reset(token)


def load_intelligence_dataset(name):
    if name not in DATASETS:raise EvaluationFixtureError('Unknown intelligence dataset.')
    path=ROOT/'datasets/intelligence'/f'{name}.jsonl'
    try:
        cases=[IntelligenceCase.model_validate_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        known=fixtures()
        if not 1<=len(cases)<=250 or len({c.case_id for c in cases})!=len(cases):raise ValueError('Empty, duplicate or unbounded cases.')
        if any(c.fixture_id not in known for c in cases):raise ValueError('Unknown input fixture.')
        return cases
    except (ValueError,OSError) as exc:raise EvaluationFixtureError(f'Invalid intelligence dataset: {name}.') from exc


def dataset_fingerprint(name):
    paths=[ROOT/'datasets/intelligence'/f'{name}.jsonl',ROOT/'fixtures/intelligence_fixtures_v2.json',ROOT/'fixtures/semantic_references_v2.json',ROOT/'fixtures/retrieval_references_v2.json']
    return sha256(b'\n'.join(p.read_bytes() for p in paths)).hexdigest()


def _at(value,path):
    for key in path.split('.'):
        value=value[int(key)] if isinstance(value,list) else value[key]
    return value


def check_expected(actual,expected):
    reasons=[]
    for path,wanted in expected.items():
        try:observed=_at(actual,path)
        except (KeyError,IndexError,TypeError,ValueError):reasons.append(path+': output path missing.');continue
        numeric=isinstance(wanted,(int,float)) and not isinstance(wanted,bool)
        equal=math.isclose(observed,wanted,rel_tol=1e-9,abs_tol=1e-6) if numeric and isinstance(observed,(int,float)) and not isinstance(observed,bool) else type(observed)==type(wanted) and observed==wanted
        if not equal:reasons.append(f'{path}: expected {wanted!r}; observed {observed!r}.')
    return reasons


def reference_measurement(actual_labels,reference):
    if reference.get('review_status')!='approved' or not reference.get('reviewer'):
        return None
    expected=reference['reference_labels'];pairs=[(expected[k],actual_labels.get(k,'missing')) for k in sorted(expected)]
    confusion={}
    for gold,actual in pairs:confusion.setdefault(gold,{}).setdefault(actual,0);confusion[gold][actual]+=1
    return dict(numerator=sum(a==b for a,b in pairs),denominator=len(pairs),mode='mocked_model_against_human_reference',confusion=confusion)


def aggregate_reports(reports,case_measurements,fingerprint):
    critical=[r for r in reports if r.critical]
    categories={};modes={};indicators={};confusion={k:0 for k in ('true_accept','false_reject','false_accept','true_reject')}
    for report,measurements in zip(reports,case_measurements):
        for table,key in ((categories,report.category),(modes,report.execution_mode)):
            row=table.setdefault(key,dict(passed=0,failed=0,skipped=0,total=0));row['total']+=1
            row[{'PASSED':'passed','FAILED':'failed','SKIPPED':'skipped'}[report.status]]+=1
        for key,value in measurements.items():
            if key=='grounding_classification':confusion[value['cell']]+=1;continue
            dest=indicators.setdefault(key,dict(numerator=0,denominator=0,mode=value['mode']))
            dest['numerator']+=value['numerator'];dest['denominator']+=value['denominator']
            if 'confusion' in value:
                for label,actuals in value['confusion'].items():
                    for actual,count in actuals.items():dest.setdefault('confusion',{}).setdefault(label,{}).setdefault(actual,0);dest['confusion'][label][actual]+=count
    contracts={
        'evidence_contract_compliance':lambda r:r.category=='evidence_reliability',
        'scoring_contract_compliance':lambda r:r.category=='deterministic_scoring',
        'canonical_decision_compliance':lambda r:r.category=='goal_comparison',
        'source_binding_compliance':lambda r:r.case_id.startswith('retrieval_binding_'),
        'recommendation_rubric_compliance':lambda r:r.category=='recommendation_quality',
        'target_binding_compliance':lambda r:r.case_id in {'recommendation_target_swap','recommendation_weak_hook','recommendation_engagement_goal'},
        'freshness_rejection_compliance':lambda r:r.case_id in {'comparison_stale_semantic','recommendation_stale_citation','retrieval_binding_revision','assistant_stale_evidence'},
        'unsupported_claim_rejection_contracts':lambda r:r.case_id in {'assistant_causal','assistant_revenue','assistant_sentiment','assistant_injection'},
        'sse_contract_compliance':lambda r:r.case_id.startswith('stream_')}
    for key,predicate in contracts.items():
        selected=[r for r in reports if predicate(r) and r.status!='SKIPPED']
        indicators[key]=dict(numerator=sum(r.status=='PASSED' for r in selected),denominator=len(selected),mode='curated_offline_contract_assertions')
    valid=confusion['true_accept']+confusion['false_reject'];invalid=confusion['false_accept']+confusion['true_reject']
    indicators.update(valid_claim_acceptance=dict(numerator=confusion['true_accept'],denominator=valid,mode='mocked_model_agent_authored_labels'),
        valid_claim_false_rejection=dict(numerator=confusion['false_reject'],denominator=valid,mode='mocked_model_agent_authored_labels'),
        invalid_claim_false_acceptance=dict(numerator=confusion['false_accept'],denominator=invalid,mode='mocked_model_agent_authored_labels'))
    indicators.setdefault('semantic_reference_agreement',dict(numerator=0,denominator=0,mode='human_review_pending'))
    for value in indicators.values():value['value']=value['numerator']/value['denominator'] if value['denominator'] else None
    return dict(methodology='offline_contracts_and_mocked_probes',dataset_version=DATASET_VERSION,evaluator=EVALUATOR,dataset_fingerprint=fingerprint,
        critical_gate=dict(passed=bool(critical) and all(r.status=='PASSED' for r in critical),passed_cases=sum(r.status=='PASSED' for r in critical),failed_cases=sum(r.status=='FAILED' for r in critical),skipped_cases=sum(r.status=='SKIPPED' for r in critical),total_cases=len(critical),policy='critical-contracts-1.0.0: every curated critical case must pass'),
        categories=categories,execution_modes=modes,indicators=indicators,grounding_confusion=confusion,
        skipped_cases=sum(r.status=='SKIPPED' for r in reports),limitations=['No live Gemini/Qdrant accuracy measured.','Agent-authored semantic reference candidates await independent human review.','Exploratory failures are retained; critical gate is not overall semantic accuracy.'])


def run_intelligence_regression(name,*,session=None,persist=False):
    cases=load_intelligence_dataset(name);known=fixtures();started=datetime.now(UTC);reports=[];measurements=[]
    references=json.loads((ROOT/'fixtures/semantic_references_v2.json').read_text(encoding='utf-8'))['references']
    with offline_boundary():
        for case in cases:
            tick=perf_counter();actual={};metrics={};reasons=[];skip=case.skip_reason;effective_mode=case.execution_mode
            try:
                if case.operation=='reference':
                    from app.evaluations.intelligence_fixtures import subject
                    measured=reference_measurement({},references[case.fixture_id])
                    if measured is not None:
                        data=subject('content_1',known[case.fixture_id],semantic=True)[3]
                        measured=reference_measurement({f['feature']:f['value'] for f in data['features']},references[case.fixture_id])
                        actual={'reviewed':True};metrics={'semantic_reference_agreement':measured};skip=None;effective_mode='mocked_model_against_human_reference'
                if not skip:
                    if case.operation!='reference':actual,metrics=execute_case(case,known[case.fixture_id])
                    reasons=check_expected(actual,case.expected)
            except Exception as exc:
                skip=None;actual={'error_type':type(exc).__name__};reasons=[f'Evaluation execution error: {type(exc).__name__}: {str(exc)[:240]}']
            status='SKIPPED' if skip else 'FAILED' if reasons else 'PASSED'
            checks={} if skip else {'contract':EvaluationCheckResult(passed=not reasons,score=0 if reasons else 1,message='; '.join(reasons) if reasons else 'Explicit expected contract matched.')}
            reports.append(EvaluationCaseReport(case_id=case.case_id,status=status,answer_type='comparison',answer_text=json.dumps(actual,ensure_ascii=False),
                rubric_results=checks,duration_ms=max(0,round((perf_counter()-tick)*1000)),category=case.category,execution_mode=effective_mode,
                critical=case.critical,fixture_id=case.fixture_id,evaluator_version=EVALUATOR,actual_output=actual,expected_output=case.expected,
                failure_reasons=reasons,skip_reason=skip,references=case.references))
            measurements.append(metrics)
    details=aggregate_reports(reports,measurements,dataset_fingerprint(name))
    details['telemetry_context']=dict(execution_mode='offline_evaluation',provider_invocation_count=0,provider_usage='not_measured',cost_events_created=False,dataset_version=DATASET_VERSION,evaluator=EVALUATOR)
    report=EvaluationRunReport(run_id=str(uuid4()),dataset=name,dataset_version=DATASET_VERSION,evaluator=EVALUATOR,status='COMPLETED',
        total_cases=len(reports),passed_cases=sum(r.status=='PASSED' for r in reports),failed_cases=sum(r.status=='FAILED' for r in reports),skipped_cases=details['skipped_cases'],
        aggregate_metrics={'_evaluation':details},evaluation_details=details,cases=reports,created_at=started,completed_at=datetime.now(UTC),persisted=False)
    if persist:
        if session is None:raise ValueError('An explicit evaluation session is required for V2 persistence.')
        persist_report(report,cases,session)
    return report


def persist_report(report,cases,session):
    from app.db.repositories.evaluation_repository import EvaluationRepository
    repo=EvaluationRepository(session);description=json.dumps(dict(methodology='offline_intelligence',fingerprint=report.evaluation_details['dataset_fingerprint']),sort_keys=True)
    existing=repo.get_dataset(name=report.dataset,version=DATASET_VERSION)
    if existing is not None and existing.description!=description:raise EvaluationFixtureError('Versioned dataset content changed; bump dataset/evaluator version before persistence.')
    dataset=existing or repo.create_dataset(name=report.dataset,version=DATASET_VERSION,source_path='bundled:intelligence/'+report.dataset,description=description)
    definitions=[EvaluationCaseDefinition(case_id=c.case_id,project_fixture=c.fixture_id,question=c.scenario,expected_answer_type='comparison',rubric=EvaluationRubric(must_compare_both_contents=True)) for c in cases]
    rows=repo.sync_cases(dataset.id,definitions);run=repo.start_run(dataset_id=dataset.id,evaluator=EVALUATOR,total_cases=len(cases))
    for result in report.cases:
        metadata=result.model_dump(mode='json',exclude={'rubric_results','answer_text'})
        repo.record_result(run_id=run.id,evaluation_case_id=rows[result.case_id].id,status=result.status,answer_type=result.answer_type,answer_text=result.answer_text,
            metric_scores=result.metric_scores,rubric_results={**{k:v.model_dump() for k,v in result.rubric_results.items()},'_evaluation':metadata},duration_ms=result.duration_ms)
    repo.complete_run(run.id,passed_cases=report.passed_cases,failed_cases=report.failed_cases,aggregate_metrics=report.aggregate_metrics)
    report.run_id=run.id;report.persisted=True
