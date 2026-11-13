"""V2 reports reuse evaluation history without overwriting legacy versions."""
from contextlib import contextmanager
from copy import deepcopy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import evaluations
from app.evaluations.regression_runner import run_regression
from app.evaluations.intelligence_models import DATASETS
from app.evaluations import intelligence_runner
from app.db.repositories.evaluation_repository import EvaluationRepository


def test_full_v2_report_roundtrip_and_read_only_api(db_session,monkeypatch):
    repository=EvaluationRepository(db_session)
    legacy=repository.create_dataset(name='creatorlens_core_v1',version='1.0.0',source_path='historical',description='Historical row')
    old=repository.start_run(dataset_id=legacy.id,evaluator='historical',total_cases=20)
    repository.complete_run(old.id,passed_cases=20,failed_cases=0,aggregate_metrics={'pass_rate':1})
    result=run_regression(DATASETS[0],session=db_session,persist=True)
    assert result.evaluation_details['critical_gate']['passed'] and result.total_cases==133
    assert result.passed_cases+result.failed_cases+result.skipped_cases==133
    assert result.skipped_cases==14
    assert result.persisted
    assert repository.get_run(old.id).aggregate_metrics=={'pass_rate':1}
    assert len(repository.list_results(result.run_id))==133
    @contextmanager
    def session():yield db_session
    monkeypatch.setattr(evaluations,'database_session',session)
    app=FastAPI();app.include_router(evaluations.router)
    with TestClient(app) as client:
        datasets=client.get('/api/evaluations/datasets').json()
        assert {d['version'] for d in datasets}=={'1.1.0','2.0.0'}
        new=next(d for d in datasets if d['name']==DATASETS[0])
        assert new['case_count']==133 and new['methodology'].startswith('offline_intelligence')
        detail=client.get('/api/evaluations/runs/'+result.run_id).json()
        assert detail['run']['skipped_cases']==14
        assert detail['run']['evaluation_details']['critical_gate']['passed']
        assert any(r['status']=='SKIPPED' and r['evaluation_details']['skip_reason'] for r in detail['results'])
        assert all('_evaluation' not in r['rubric_results'] for r in detail['results'])
        old_detail=client.get('/api/evaluations/runs/'+old.id).json()
        assert old_detail['run']['evaluation_details']=={} and old_detail['run']['dataset_version']=='1.0.0'
    # Prevent changing the meaning of a persisted dataset version.
    dataset=repository.get_dataset(name=DATASETS[0],version='2.0.0');dataset.description='a different fixture fingerprint'
    import pytest
    with pytest.raises(ValueError):intelligence_runner.persist_report(result,intelligence_runner.load_intelligence_dataset(DATASETS[0]),db_session)


def test_report_is_reproducible_apart_from_run_identity_and_timing(monkeypatch):
    full=intelligence_runner.load_intelligence_dataset(DATASETS[0])
    selected=[c for c in full if c.operation not in {'stream','reference','deferred'}][:20]
    monkeypatch.setattr(intelligence_runner,'load_intelligence_dataset',lambda _:selected)
    one=intelligence_runner.run_intelligence_regression(DATASETS[0]);two=intelligence_runner.run_intelligence_regression(DATASETS[0])
    assert one.evaluation_details==two.evaluation_details
    assert [r.actual_output for r in one.cases]==[r.actual_output for r in two.cases]
    assert [r.status for r in one.cases]==[r.status for r in two.cases]
