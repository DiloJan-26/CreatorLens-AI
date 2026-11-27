"""Publication safety and real deterministic report contracts; no providers."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest
from app.evaluations import publication as pub
from app.evaluations.regression_runner import run_regression


@pytest.fixture
def smoke():return run_regression("creatorlens_ci_smoke_v1",persist=False)


@pytest.mark.parametrize("name",["../private","unknown","creatorlens_core_v1/.."])
def test_unregistered_dataset_cannot_start_execution(monkeypatch,name):
    monkeypatch.setattr(subprocess,"run",lambda *a,**k:pytest.fail("Unknown dataset executed"))
    with pytest.raises(ValueError):pub.execute_offline(name)


@pytest.mark.parametrize("damage",["duplicate","missing","counts","dataset","evaluator","version"])
def test_report_contract_rejects_modified_identity_or_accounting(smoke,damage):
    report=deepcopy(smoke)
    if damage=="duplicate":report.cases[1]=deepcopy(report.cases[0])
    if damage=="missing":report.cases.pop()
    if damage=="counts":report.passed_cases=0
    if damage=="dataset":report.dataset="creatorlens_core_v1"
    if damage=="evaluator":report.evaluator="forged-evaluator"
    if damage=="version":report.dataset_version="9.0.0"
    with pytest.raises(ValueError):pub.validate_report(report,"creatorlens_ci_smoke_v1")


def test_original_legacy_numerical_metrics_are_unchanged(smoke):
    before=deepcopy(smoke.aggregate_metrics)
    version,*_=pub.validate_report(smoke,smoke.dataset)
    assert version=="1.1.0" and smoke.aggregate_metrics==before and before["pass_rate"]==1


def test_source_fingerprint_ignores_secrets_and_runtime_but_detects_code(tmp_path,monkeypatch):
    (tmp_path/"app").mkdir();source=tmp_path/"app/main.py";source.write_text("x=1")
    monkeypatch.setattr(pub,"BACKEND",tmp_path)
    first=pub.source_fingerprint()
    (tmp_path/".env").write_text("NEVER_PRINT=private");(tmp_path/"app/cache.pyc").write_bytes(b"cache")
    assert pub.source_fingerprint()==first
    source.write_text("x=2");assert pub.source_fingerprint()!=first


@pytest.mark.parametrize("sha",["latest","abc","g"*40,"0"*39])
def test_source_commit_identifiers_are_exact(sha):
    with pytest.raises(ValueError):pub.source_identity(sha)


def test_mismatched_commit_is_rejected(monkeypatch):
    def git(args,**kwargs):return SimpleNamespace(stdout="1"*40 if "HEAD" in args else "" if "status" in args else str(pub.BACKEND.parent))
    monkeypatch.setattr(pub.subprocess,"run",git)
    with pytest.raises(ValueError,match="differs"):pub.source_identity("2"*40)


def test_timeout_is_a_specific_safe_execution_failure(monkeypatch):
    def timeout(*a,**k):raise subprocess.TimeoutExpired("private-command",pub.MAX_SECONDS,stderr="private-secret")
    monkeypatch.setattr(pub.subprocess,"run",timeout)
    with pytest.raises(pub.EvaluationExecutionError,match="EVALUATION_TIMEOUT") as error:pub.execute_offline("creatorlens_ci_smoke_v1")
    assert "private" not in str(error.value)


def test_missing_child_report_is_not_a_successful_run(monkeypatch):
    monkeypatch.setattr(pub.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0))
    with pytest.raises(pub.EvaluationExecutionError,match="PROCESS_FAILED"):pub.execute_offline("creatorlens_ci_smoke_v1")


def test_preview_does_not_open_a_database(monkeypatch,smoke,capsys):
    from app.db import session
    monkeypatch.setattr(session,"database_session",lambda:pytest.fail("Preview accessed a database"))
    monkeypatch.setattr(pub,"source_identity",lambda *a:dict(source_fingerprint="s"*64,source_commit=None,source_state="unknown"))
    monkeypatch.setattr(pub,"execute_offline",lambda name:deepcopy(smoke))
    assert pub.main(["--dataset",smoke.dataset])==0
    assert '"persisted": false' in capsys.readouterr().out


@pytest.mark.parametrize("args",[["--publish"],["--publish","--database-name","creatorlensdb"],["--database-name","creatorlensdb"],["--rerun"]])
def test_publication_requires_explicit_target_and_commit(monkeypatch,args):
    monkeypatch.setattr(pub,"execute_offline",lambda *a:pytest.fail("Execution started without confirmation"))
    with pytest.raises(SystemExit) as error:pub.main(["--dataset","creatorlens_ci_smoke_v1",*args])
    assert error.value.code==2


def test_wrong_database_target_fails_before_execution(monkeypatch,capsys):
    from app.core import config
    monkeypatch.setattr(config,"get_settings",lambda:SimpleNamespace(sqlalchemy_database_url=lambda:"postgresql://user:SECRET@localhost/other"))
    monkeypatch.setattr(pub,"execute_offline",lambda *a:pytest.fail("Wrong target executed"))
    with pytest.raises(SystemExit):pub.main(["--dataset","creatorlens_ci_smoke_v1","--publish","--database-name","creatorlensdb","--source-commit","0"*40])
    assert "SECRET" not in capsys.readouterr().err


def test_fingerprints_are_portable_between_windows_and_linux(tmp_path,monkeypatch):
    (tmp_path/'app').mkdir();source=tmp_path/'app/main.py';source.write_bytes(b'x=1\ny=2\n')
    monkeypatch.setattr(pub,'BACKEND',tmp_path)
    first=pub.source_fingerprint();source.write_bytes(b'x=1\r\ny=2\r\n')
    assert pub.source_fingerprint()==first
    dataset=tmp_path/'creatorlens_ci_smoke_v1.jsonl';fixtures=tmp_path/'fixtures.json'
    dataset.write_bytes(b'case\n');fixtures.write_bytes(b'fixture\n')
    monkeypatch.setattr(pub,'DATASETS_DIR',tmp_path);monkeypatch.setattr(pub,'FIXTURES_PATH',fixtures)
    first=pub.canonical_dataset_fingerprint('creatorlens_ci_smoke_v1')
    dataset.write_bytes(b'case\r\n');fixtures.write_bytes(b'fixture\r\n')
    assert pub.canonical_dataset_fingerprint('creatorlens_ci_smoke_v1')==first
