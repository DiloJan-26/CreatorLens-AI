"""Actual evaluator -> existing SQL history -> API. Isolated SQLite only."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,UTC
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.api import evaluations
from app.db.models.evaluation import EvaluationRun,EvaluationResult,EvaluationCase
from app.db.repositories.evaluation_repository import EvaluationRepository
from app.evaluations import publication as pub
from app.evaluations.regression_runner import run_regression


@pytest.fixture
def publish(db_session,monkeypatch):
    identity=dict(source_fingerprint="a"*64,source_commit="b"*40,source_commit_origin="git",source_state="clean")
    monkeypatch.setattr(pub,"source_identity",lambda *a:dict(identity))
    monkeypatch.setattr(evaluations,"source_fingerprint",lambda:identity["source_fingerprint"])
    monkeypatch.setattr(pub,"execute_offline",lambda name:run_regression(name,persist=False))
    @contextmanager
    def database():
        with db_session.begin_nested():yield db_session
    monkeypatch.setattr(evaluations,"database_session",database)
    app=FastAPI();app.include_router(evaluations.router)
    with TestClient(app) as client:yield client,identity


def test_publication_roundtrip_reloads_actual_results_and_release_identity(db_session,publish):
    client,identity=publish
    assert client.get("/api/evaluations/runs").json()==[]
    response=client.post("/api/evaluations/runs",json={"dataset":"creatorlens_ci_smoke_v1"})
    assert response.status_code==200,response.text
    result=response.json();assert result["persisted"] and result["passed_cases"]==5
    rows=client.get("/api/evaluations/runs").json();assert len(rows)==1
    run=rows[0]
    assert run["publication"]["source_commit"]==identity["source_commit"] and run["source_status"]=="current"
    assert run["publication"]["provider_invocation_count"]==0
    detail=client.get("/api/evaluations/runs/"+run["id"]).json()
    assert len(detail["results"])==5 and all(r["scenario"] and r["answer_text"] for r in detail["results"])
    assert all("_evaluation" not in r["rubric_results"] for r in detail["results"])
    before=db_session.scalar(select(func.count()).select_from(EvaluationRun))
    client.get("/api/evaluations/runs");client.get("/api/evaluations/datasets")
    assert db_session.scalar(select(func.count()).select_from(EvaluationRun))==before
    assert result["aggregate_metrics"]["pass_rate"]==1


def test_duplicate_publication_returns_original_history_and_rerun_preserves_it(db_session,publish):
    first=pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session)
    original=first.model_dump(mode="json")
    second=pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session)
    assert second.run_id==first.run_id and second.created_at==first.created_at
    assert [c.model_dump() for c in first.cases]==[c.model_dump() for c in second.cases]
    assert db_session.scalar(select(func.count()).select_from(EvaluationRun))==1
    assert db_session.scalar(select(func.count()).select_from(EvaluationResult))==5
    third=pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session,rerun=True)
    assert third.run_id!=first.run_id
    assert db_session.get(EvaluationRun,first.run_id).aggregate_metrics==original["aggregate_metrics"]


def test_full_intelligence_publication_retains_all_skips_and_distinct_measurements(db_session,publish):
    client,_=publish
    report=pub.evaluate_and_publish("creatorlens_intelligence_v2",session=db_session)
    assert (report.passed_cases,report.failed_cases,report.skipped_cases)==(119,0,14)
    detail=client.get("/api/evaluations/runs/"+report.run_id).json()
    assert len(detail["results"])==133
    assert detail["run"]["evaluation_details"]["critical_gate"]["passed_cases"]==96
    assert all(r["evaluation_details"]["skip_reason"] for r in detail["results"] if r["status"]=="SKIPPED")
    assert "pass_rate" not in detail["run"]["aggregate_metrics"]
    assert detail["run"]["evaluation_details"]["indicators"]["semantic_reference_agreement"]["denominator"]==0


def test_timeout_is_persisted_as_failed_execution_without_fabricated_cases(db_session,publish,monkeypatch):
    client,_=publish
    def timeout(name):raise pub.EvaluationExecutionError("EVALUATION_TIMEOUT")
    monkeypatch.setattr(pub,"execute_offline",timeout)
    result=client.post("/api/evaluations/runs",json={"dataset":"creatorlens_ci_smoke_v1"}).json()
    assert result["status"]=="FAILED" and result["error_code"]=="EVALUATION_TIMEOUT"
    run=client.get("/api/evaluations/runs").json()[0]
    assert run["status"]=="FAILED" and run["publication"]["not_executed_cases"]==5
    assert not client.get("/api/evaluations/runs/"+run["id"]).json()["results"]


def test_partial_database_failure_rolls_back_publication(db_session,publish,monkeypatch):
    client,_=publish
    original=EvaluationRepository.record_result;count=0
    def fail(self,**kwargs):
        nonlocal count
        count+=1
        if count==3:raise RuntimeError("Synthetic write failure")
        return original(self,**kwargs)
    monkeypatch.setattr(EvaluationRepository,"record_result",fail)
    response=client.post("/api/evaluations/runs",json={"dataset":"creatorlens_ci_smoke_v1"})
    assert response.status_code==503
    assert not db_session.scalar(select(EvaluationRun.id)) and not db_session.scalar(select(EvaluationResult.id))


def test_different_source_is_not_labeled_current_and_legacy_provenance_is_unknown(db_session,publish):
    client,identity=publish
    report=pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session)
    identity["source_fingerprint"]="c"*64
    assert client.get("/api/evaluations/runs/"+report.run_id).json()["run"]["source_status"]=="different"
    repo=EvaluationRepository(db_session);dataset=repo.create_dataset(name="creatorlens_core_v1",version="1.0.0",source_path="historical")
    old=repo.start_run(dataset_id=dataset.id,evaluator="historical",total_cases=20)
    repo.complete_run(old.id,passed_cases=20,failed_cases=0,aggregate_metrics={"pass_rate":1})
    row=client.get("/api/evaluations/runs/"+old.id).json()["run"]
    assert row["source_status"]=="unverified" and row["publication"]=={} and row["dataset_version"]=="1.0.0"


def test_hidden_datasets_do_not_displace_supported_history_before_limit(db_session,publish):
    client,_=publish;report=pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session)
    repo=EvaluationRepository(db_session);hidden=repo.create_dataset(name="private_fixture",version="1",source_path="internal")
    for _ in range(21):repo.start_run(dataset_id=hidden.id,evaluator="private",total_cases=1)
    rows=client.get("/api/evaluations/runs?limit=1").json()
    assert [r["id"] for r in rows]==[report.run_id]


def test_definition_drift_requires_new_version_and_does_not_rewrite_history(db_session,publish):
    client,_=publish;report=pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session)
    row=db_session.scalar(select(EvaluationCase));row.question="Old reference meaning";db_session.flush()
    with pytest.raises(ValueError):pub.evaluate_and_publish("creatorlens_ci_smoke_v1",session=db_session,rerun=True)
    assert row.question=="Old reference meaning" and len(EvaluationRepository(db_session).list_runs())==1


def test_real_isolated_child_executes_without_provider_credentials(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY","never-send-this-fixture")
    result=pub.execute_offline("creatorlens_ci_smoke_v1")
    assert result.total_cases==5 and result.failed_cases==0 and not result.persisted


def test_failed_contracts_are_published_without_changing_expectations(db_session,publish,monkeypatch):
    client,_=publish
    report=run_regression('creatorlens_ci_smoke_v1',persist=False)
    report.cases[0].status='FAILED';report.cases[0].rubric_results['faithfulness_quality'].passed=False
    report.cases[0].rubric_results['faithfulness_quality'].message='Synthetic unsupported answer.'
    report.passed_cases-=1;report.failed_cases+=1;report.aggregate_metrics['pass_rate']=.8
    monkeypatch.setattr(pub,'execute_offline',lambda name:deepcopy(report))
    published=pub.evaluate_and_publish(report.dataset,session=db_session)
    detail=client.get('/api/evaluations/runs/'+published.run_id).json()
    assert detail['run']['passed_cases']==4 and detail['run']['failed_cases']==1
    assert any(row['status']=='FAILED' and row['evaluation_details']['failure_reasons'] for row in detail['results'])


def test_source_changes_reject_publication_without_database_rows(db_session,publish,monkeypatch):
    _,identity=publish;count=0
    def changed(*args):
        nonlocal count
        count+=1
        return {**identity,'source_fingerprint':('a' if count==1 else 'f')*64}
    monkeypatch.setattr(pub,'source_identity',changed)
    with pytest.raises(ValueError,match='Source changed'):pub.evaluate_and_publish('creatorlens_ci_smoke_v1',session=db_session)
    assert not db_session.scalar(select(EvaluationRun.id))


def test_new_execution_failure_is_not_hidden_by_a_previous_passing_run(db_session,publish,monkeypatch):
    client,_=publish
    first=pub.evaluate_and_publish('creatorlens_ci_smoke_v1',session=db_session)
    def failure(name):raise pub.EvaluationExecutionError('EVALUATION_PROCESS_FAILED')
    monkeypatch.setattr(pub,'execute_offline',failure)
    latest=pub.evaluate_and_publish('creatorlens_ci_smoke_v1',session=db_session)
    assert latest.run_id!=first.run_id and latest.status=='FAILED'
    assert client.get('/api/evaluations/runs').json()[0]['status']=='FAILED'
    assert db_session.get(EvaluationRun,first.run_id).passed_cases==5


def test_operator_publish_requires_confirmation_and_writes_only_supplied_session(db_session,publish,monkeypatch,capsys):
    from app.core import config
    from app.db import session as session_module
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(sqlalchemy_database_url=lambda:'postgresql://fixture:PRIVATE@localhost/isolated'))
    @contextmanager
    def database():
        with db_session.begin_nested():yield db_session
    monkeypatch.setattr(session_module,'database_session',database)
    assert pub.main(['--dataset','creatorlens_ci_smoke_v1','--publish','--database-name','isolated','--source-commit','b'*40])==0
    output=capsys.readouterr().out
    assert '"persisted": true' in output and 'PRIVATE' not in output
    assert len(EvaluationRepository(db_session).list_runs())==1


def test_changed_results_for_same_release_are_preserved_instead_of_reusing_a_pass(db_session,publish,monkeypatch):
    client,_=publish
    first=pub.evaluate_and_publish('creatorlens_ci_smoke_v1',session=db_session)
    changed=run_regression('creatorlens_ci_smoke_v1',persist=False)
    changed.cases[0].status='FAILED';changed.cases[0].rubric_results['faithfulness_quality'].passed=False
    changed.passed_cases=4;changed.failed_cases=1;changed.aggregate_metrics['pass_rate']=.8
    monkeypatch.setattr(pub,'execute_offline',lambda name:deepcopy(changed))
    latest=pub.evaluate_and_publish(changed.dataset,session=db_session)
    assert latest.run_id!=first.run_id and latest.failed_cases==1
    assert latest.aggregate_metrics['_publication']['non_reproducible_result']
    assert db_session.get(EvaluationRun,first.run_id).passed_cases==5
    assert client.get('/api/evaluations/runs').json()[0]['failed_cases']==1


def test_case_details_use_one_batched_definition_query(db_session,publish):
    from sqlalchemy import event
    client,_=publish;report=pub.evaluate_and_publish('creatorlens_ci_smoke_v1',session=db_session)
    queries=[]
    def observe(connection,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'evaluation_cases' in statement:queries.append(statement)
    engine=db_session.get_bind();event.listen(engine,'before_cursor_execute',observe)
    try:response=client.get('/api/evaluations/runs/'+report.run_id)
    finally:event.remove(engine,'before_cursor_execute',observe)
    assert response.status_code==200 and len(response.json()['results'])==5
    assert len(queries)==1
