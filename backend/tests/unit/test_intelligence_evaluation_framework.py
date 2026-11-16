"""Framework accounting and independent-fixture contracts, not model accuracy claims."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from app.evaluations import intelligence_runner as runner
from app.evaluations.intelligence_models import IntelligenceCase,DATASETS
from app.schemas.evaluation import EvaluationCaseReport


def report(case_id='example',status='PASSED',critical=False,category='assistant_grounding'):
    return EvaluationCaseReport(case_id=case_id,status=status,critical=critical,category=category,execution_mode='mocked_model',answer_type='comparison',answer_text='synthetic',duration_ms=0)


def test_dataset_ids_versions_and_legacy_separation():
    full=runner.load_intelligence_dataset(DATASETS[0]);smoke=runner.load_intelligence_dataset(DATASETS[1])
    assert len(full)==133 and len(smoke)==23
    assert {c.case_id for c in smoke}<={c.case_id for c in full}
    assert all(c.critical and not c.skip_reason for c in smoke)
    assert len({c.case_id for c in full})==len(full)
    from app.evaluations.fixture_loader import load_dataset,DATASET_VERSION
    assert DATASET_VERSION=='1.1.0'
    assert len(load_dataset('creatorlens_core_v1'))==20 and len(load_dataset('creatorlens_ci_smoke_v1'))==5


@pytest.mark.parametrize('change',[{'category':'invented'},{'dataset_version':'wrong'},{'critical':True,'skip_reason':'not allowed'},{'expected':{},'skip_reason':None}])
def test_invalid_case_definitions_rejected(change):
    payload=runner.load_intelligence_dataset(DATASETS[0])[0].model_dump();payload.update(change)
    with pytest.raises(ValueError):IntelligenceCase.model_validate(payload)


@pytest.mark.parametrize('name',['../private','unknown','creatorlens_intelligence_v2/..'])
def test_dataset_registry_blocks_arbitrary_paths(name):
    with pytest.raises(ValueError):runner.load_intelligence_dataset(name)


def test_duplicate_ids_fail_loader(monkeypatch,tmp_path):
    first=runner.load_intelligence_dataset(DATASETS[0])[0].model_dump()
    directory=tmp_path/'datasets/intelligence';directory.mkdir(parents=True)
    (directory/(DATASETS[0]+'.jsonl')).write_text(json.dumps(first)+'\n'+json.dumps(first),encoding='utf-8')
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    with pytest.raises(ValueError):runner.load_intelligence_dataset(DATASETS[0])


@pytest.mark.parametrize('actual,expected,passes',[({'n':1.2},{'n':1.2},True),({'n':False},{'n':0},False),({'n':None},{'n':None},True),({}, {'missing':0},False),({'items':[2]},{'items.0':2},True)])
def test_explicit_expectation_checks_do_not_invent_missing_values(actual,expected,passes):
    assert (not runner.check_expected(actual,expected))==passes


def test_pass_fail_skip_and_critical_gate_are_separate():
    rows=[report('critical',critical=True),report('exploratory','FAILED'),report('review','SKIPPED')]
    summary=runner.aggregate_reports(rows,[{}, {}, {}],'fingerprint')
    assert summary['critical_gate']['passed'] is True
    assert summary['categories']['assistant_grounding']==dict(passed=1,failed=1,skipped=1,total=3)
    assert summary['skipped_cases']==1
    assert summary['indicators']['semantic_reference_agreement']['value'] is None
    assert 'pass_rate' not in summary


@pytest.mark.parametrize('state',['FAILED','SKIPPED'])
def test_critical_failure_or_skip_never_passes_gate(state):
    assert not runner.aggregate_reports([report(status=state,critical=True)],[{}],'x')['critical_gate']['passed']


def test_false_accept_and_false_reject_have_distinct_denominators():
    rows=[report(str(i)) for i in range(4)]
    cells=['true_accept','false_reject','false_accept','true_reject']
    result=runner.aggregate_reports(rows,[{'grounding_classification':{'cell':cell}} for cell in cells],'x')
    assert result['indicators']['valid_claim_false_rejection']['numerator']==1
    assert result['indicators']['valid_claim_false_rejection']['denominator']==2
    assert result['indicators']['invalid_claim_false_acceptance']['value']==.5


def test_human_reference_measurement_requires_real_review_metadata():
    pending=dict(reference_labels={'hook':'clear','cta':'absent'},review_status='pending_human_review',reviewer=None)
    assert runner.reference_measurement({'hook':'clear'},pending) is None
    # Unit-only approval record exercises arithmetic; it does not approve the shipped reference candidates.
    approved={**pending,'review_status':'approved','reviewer':'unit-test-only'}
    measured=runner.reference_measurement({'hook':'clear','cta':'partial'},approved)
    assert measured['numerator']==1 and measured['denominator']==2
    assert measured['confusion']['absent']['partial']==1
    refs=json.loads((runner.ROOT/'fixtures/semantic_references_v2.json').read_text(encoding='utf-8'))['references']
    assert all(r['review_status']=='pending_human_review' and r['reviewer'] is None for r in refs.values())


def test_execution_errors_record_failure_instead_of_disappearing(monkeypatch):
    case=runner.load_intelligence_dataset(DATASETS[0])[0]
    monkeypatch.setattr(runner,'load_intelligence_dataset',lambda _: [case])
    def fail(*args):raise RuntimeError('synthetic evaluation failure')
    monkeypatch.setattr(runner,'execute_case',fail)
    result=runner.run_intelligence_regression(DATASETS[0])
    assert result.total_cases==1 and result.failed_cases==1
    assert result.cases[0].failure_reasons and not result.evaluation_details['critical_gate']['passed']


def test_network_guard_blocks_remote_calls_and_restores_context():
    import socket
    with runner.offline_boundary():
        with pytest.raises(RuntimeError):socket.getaddrinfo('external.invalid',443)
    assert not runner._ACTIVE.get()


def test_explicit_no_persist_overrides_supplied_session(monkeypatch):
    from app.evaluations.regression_runner import run_regression
    captured={}
    def fake(name,**kwargs):captured.update(kwargs);return object()
    monkeypatch.setattr(runner,'run_intelligence_regression',fake)
    run_regression(DATASETS[0],session=object(),persist=False)
    assert captured['persist'] is False
