"""Explicit operator publication of isolated evaluations; never used by read requests.

Preview: python -m app.evaluations.publication --dataset creatorlens_ci_smoke_v1
Publish requires --publish --database-name <target> --source-commit <release SHA>.
No provider calls, fixture imports from users, automatic schedules or schema changes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, UTC
from hashlib import sha256
import json
from importlib.metadata import version as package_version, PackageNotFoundError
import platform
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from sqlalchemy import select, text
from app.evaluations.fixture_loader import DATASET_VERSION, FIXTURES_PATH, DATASETS_DIR, EvaluationFixtureError, load_dataset, list_datasets
from app.evaluations.intelligence_models import DATASETS, DATASET_VERSION as V2_VERSION, EVALUATOR
from app.schemas.evaluation import EvaluationRunReport, EvaluationCaseDefinition, EvaluationRubric

POLICY = "evaluation-publication-1.0.0"
BACKEND = Path(__file__).resolve().parents[2]
MAX_SECONDS = 180


class EvaluationExecutionError(RuntimeError):
    def __init__(self, code):
        self.code=code
        super().__init__(code)


def supported_datasets():
    return tuple(sorted(set(list_datasets()) | set(DATASETS)))


def dataset_contract(name):
    if name not in supported_datasets():
        raise EvaluationFixtureError("Unknown bundled evaluation dataset.")
    if name in DATASETS:
        from app.evaluations.intelligence_runner import load_intelligence_dataset, dataset_fingerprint
        cases=load_intelligence_dataset(name)
        definitions=[EvaluationCaseDefinition(case_id=c.case_id,project_fixture=c.fixture_id,question=c.scenario,
            expected_answer_type="comparison",rubric=EvaluationRubric(must_compare_both_contents=True)) for c in cases]
        return V2_VERSION,EVALUATOR,dataset_fingerprint(name),definitions
    from app.evaluations.regression_runner import EVALUATOR_NAME
    cases=load_dataset(name)
    fingerprint=sha256((DATASETS_DIR/(name+".jsonl")).read_bytes()+b"\n"+FIXTURES_PATH.read_bytes()).hexdigest()
    return DATASET_VERSION,EVALUATOR_NAME,fingerprint,cases



def canonical_dataset_fingerprint(name):
    # Text checkouts may use CRLF locally and LF in deployed containers.
    if name in DATASETS:
        base=Path(__file__).parent
        paths=[base/"datasets/intelligence"/(name+".jsonl"),base/"fixtures/intelligence_fixtures_v2.json",
            base/"fixtures/semantic_references_v2.json",base/"fixtures/retrieval_references_v2.json"]
    else:paths=[DATASETS_DIR/(name+".jsonl"),FIXTURES_PATH]
    return sha256(b"\n".join(p.read_bytes().replace(b"\r\n",b"\n") for p in paths)).hexdigest()


def source_fingerprint():
    paths=sorted(p for p in (BACKEND/"app").rglob("*") if p.is_file() and p.suffix in {".py",".json",".jsonl",".txt",".j2",".yaml",".yml"})
    requirements=BACKEND/"requirements.txt"
    if requirements.is_file():paths.append(requirements)
    digest=sha256()
    for path in paths:
        digest.update(path.relative_to(BACKEND).as_posix().encode()+b"\0"+path.read_bytes().replace(b"\r\n",b"\n")+b"\0")
    return digest.hexdigest()


def source_identity(commit=None):
    """Fingerprint executable backend sources, excluding credentials and runtime data."""
    if commit is not None and not re.fullmatch(r"[0-9a-fA-F]{40}",commit):
        raise ValueError("Source commit must be a full 40-character Git SHA.")
    fingerprint=source_fingerprint()
    detected=None;state="unknown"
    try:
        root=subprocess.run(["git","-c","safe.directory="+str(BACKEND.parent),"rev-parse","--show-toplevel"],cwd=BACKEND,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        detected=subprocess.run(["git","-c","safe.directory="+root,"rev-parse","HEAD"],cwd=BACKEND,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        dirty=subprocess.run(["git","-c","safe.directory="+root,"status","--porcelain","--","backend"],cwd=root,capture_output=True,text=True,timeout=5,check=True).stdout
        state="modified" if dirty.strip() else "clean"
    except (OSError,subprocess.SubprocessError):pass
    if detected and commit and detected.lower()!=commit.lower():
        raise ValueError("Supplied commit differs from the checked-out source.")
    return dict(source_fingerprint=fingerprint,source_commit=(commit or detected or None),
        source_commit_origin="git" if detected else "operator_supplied" if commit else "unavailable",source_state=state)


def execute_offline(name):
    """Existing credential-independent runner in a bounded, disposable child process."""
    dataset_contract(name)
    with tempfile.TemporaryDirectory(prefix="creatorlens-publication-") as folder:
        output=Path(folder)/"report.json"
        try:
            result=subprocess.run([sys.executable,"-m","app.evaluations.offline_runner","--dataset",name,
                "--strict","--output",str(output)],cwd=BACKEND,capture_output=True,text=True,encoding="utf-8",timeout=MAX_SECONDS)
        except subprocess.TimeoutExpired:
            raise EvaluationExecutionError("EVALUATION_TIMEOUT") from None
        except OSError:
            raise EvaluationExecutionError("EVALUATION_PROCESS_UNAVAILABLE") from None
        if result.returncode not in {0,1} or not output.is_file():
            raise EvaluationExecutionError("EVALUATION_PROCESS_FAILED")
        try:return EvaluationRunReport.model_validate_json(output.read_text(encoding="utf-8"))
        except (ValueError,OSError):raise EvaluationExecutionError("EVALUATION_REPORT_INVALID") from None


def validate_report(report,name):
    version,evaluator,fingerprint,definitions=dataset_contract(name)
    ids=[case.case_id for case in report.cases]
    if (report.dataset!=name or report.evaluator!=evaluator or report.status!="COMPLETED"
            or report.dataset_version not in {None,version} or len(ids)!=len(set(ids))
            or set(ids)!={case.case_id for case in definitions} or report.total_cases!=len(ids)
            or report.passed_cases!=sum(c.status=="PASSED" for c in report.cases)
            or report.failed_cases!=sum(c.status=="FAILED" for c in report.cases)
            or report.skipped_cases!=sum(c.status=="SKIPPED" for c in report.cases)):
        raise EvaluationFixtureError("Evaluation report does not match the bundled dataset contract.")
    if name in DATASETS and report.evaluation_details.get("dataset_fingerprint")!=fingerprint:
        raise EvaluationFixtureError("Evaluation fixture fingerprint changed.")
    # Fail closed on invalid numeric payloads rather than writing JSON NaN/Infinity.
    json.dumps(report.model_dump(mode="json"),allow_nan=False)
    report.dataset_version=version
    return version,evaluator,fingerprint,definitions


def publication_metadata(name,source):
    version,evaluator,_,_=dataset_contract(name)
    fingerprint=canonical_dataset_fingerprint(name)
    dependencies={}
    for package in ("pydantic","sqlalchemy","ragas","deepeval","langchain"):
        try:dependencies[package]=package_version(package)
        except PackageNotFoundError:dependencies[package]="not_installed"
    environment=dict(python_version=platform.python_version(),dependency_versions=dependencies)
    identity=dict(dataset=name,dataset_version=version,evaluator=evaluator,dataset_fingerprint=fingerprint,**source,**environment)
    return dict(policy_version=POLICY,fingerprint_policy="text-lf-sha256-1.0.0",publication_key=sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
        **identity,execution_mode="offline_regression",reference_scope="curated_fixtures",provider_invocation_count=0,
        published_at=datetime.now(UTC).isoformat())


def persist_report(session,report,publication,*,rerun=False):
    """Atomic history publication, serialized per release/dataset in PostgreSQL."""
    from app.db.models.evaluation import EvaluationRun
    from app.db.repositories.evaluation_repository import EvaluationRepository
    if report.status=="COMPLETED":
        _,_,_,definitions=validate_report(report,report.dataset)
    else:
        _,_,_,definitions=dataset_contract(report.dataset)
    repo=EvaluationRepository(session)
    if session.get_bind().dialect.name=="postgresql":
        lock=int(publication["publication_key"][:16],16)
        if lock>=2**63:lock-=2**64
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":lock})
    existing=session.scalar(select(EvaluationRun).where(
        EvaluationRun.aggregate_metrics["_publication"]["publication_key"].as_string()==publication["publication_key"],
        EvaluationRun.status=="COMPLETED").order_by(EvaluationRun.created_at.desc()).limit(1))
    if existing is not None and report.status=="COMPLETED":
        identical=existing.aggregate_metrics.get("_publication",{}).get("result_fingerprint")==publication.get("result_fingerprint")
        if identical and not rerun:return existing.id,True
        if not identical:publication["non_reproducible_result"]=True
    dataset=repo.get_dataset(name=report.dataset,version=report.dataset_version)
    if dataset is None:
        description=json.dumps(dict(methodology="offline_intelligence",fingerprint=publication["dataset_fingerprint"]),sort_keys=True) if report.dataset in DATASETS else "CreatorLens deterministic RAG regression dataset."
        dataset=repo.create_dataset(name=report.dataset,version=report.dataset_version,source_path="bundled:"+report.dataset,description=description)
    if report.dataset in DATASETS:
        expected_description=json.dumps(dict(methodology="offline_intelligence",fingerprint=publication["dataset_fingerprint"]),sort_keys=True)
        raw_fingerprint=dataset_contract(report.dataset)[2]
        historical_description=json.dumps(dict(methodology="offline_intelligence",fingerprint=raw_fingerprint),sort_keys=True)
        if dataset.description not in {expected_description,historical_description}:
            # Earlier publications may have captured a Windows byte fingerprint.
            previous=session.scalar(select(EvaluationRun.id).where(EvaluationRun.dataset_id==dataset.id,
                EvaluationRun.aggregate_metrics["_publication"]["dataset_fingerprint"].as_string()==publication["dataset_fingerprint"]).limit(1))
            try:description=json.loads(dataset.description or "{}")
            except ValueError:description={}
            if not previous or description.get("methodology")!="offline_intelligence":
                raise EvaluationFixtureError("Versioned dataset content changed; bump its version before publication.")
    previous_fingerprint=session.scalar(select(EvaluationRun.aggregate_metrics).where(EvaluationRun.dataset_id==dataset.id,
        EvaluationRun.aggregate_metrics["_publication"]["policy_version"].as_string()==POLICY).order_by(EvaluationRun.created_at.desc()).limit(1))
    if previous_fingerprint and previous_fingerprint["_publication"]["dataset_fingerprint"]!=publication["dataset_fingerprint"]:
        raise EvaluationFixtureError("Published dataset content changed; a new version is required.")
    # Never rewrite the shared case definitions referenced by historical runs.
    rows={c.case_key:c for c in repo.list_cases(dataset.id)}
    if set(rows)-{d.case_id for d in definitions}:raise EvaluationFixtureError("Stored dataset case identities changed.")
    for definition in definitions:
        old=rows.get(definition.case_id)
        if old is not None:
            fields=dict(project_fixture=definition.project_fixture,question=definition.question,expected_answer_type=definition.expected_answer_type,
                required_sources=definition.required_sources,forbidden_claims=definition.forbidden_claims,rubric=definition.rubric.model_dump())
            if any(getattr(old,k)!=value for k,value in fields.items()):
                raise EvaluationFixtureError("Stored case meaning changed; a new dataset version is required.")
        else:rows[definition.case_id]=repo.add_case(dataset.id,definition)
    run=repo.start_run(dataset_id=dataset.id,evaluator=report.evaluator,total_cases=report.total_cases)
    for case in report.cases:
        metadata=case.model_dump(mode="json",exclude={"rubric_results","answer_text"})
        if not metadata.get("failure_reasons"):
            metadata["failure_reasons"]=[c.message for c in case.rubric_results.values() if not c.passed]
        repo.record_result(run_id=run.id,evaluation_case_id=rows[case.case_id].id,status=case.status,
            answer_type=case.answer_type,answer_text=case.answer_text,citation_labels=case.citation_labels,
            metric_scores=case.metric_scores,rubric_results={**{k:v.model_dump() for k,v in case.rubric_results.items()},"_evaluation":metadata},
            duration_ms=case.duration_ms,error_code="CONTRACT_FAILED" if case.status=="FAILED" else None)
    run.created_at=report.created_at
    report.aggregate_metrics={**report.aggregate_metrics,"_publication":publication}
    repo.complete_run(run.id,passed_cases=report.passed_cases,failed_cases=report.failed_cases,aggregate_metrics=report.aggregate_metrics)
    run.completed_at=report.completed_at
    if report.status=="FAILED":
        repo.fail_run(run.id,error_code=report.error_code or "EVALUATION_EXECUTION_FAILED")
        run.completed_at=report.completed_at
    session.flush()
    return run.id,False


def evaluate_and_publish(name,*,session=None,commit=None,rerun=False):
    source=source_identity(commit)
    metadata=publication_metadata(name,source)
    started=datetime.now(UTC)
    try:
        report=execute_offline(name)
        validate_report(report,name)
    except EvaluationExecutionError as exc:
        version,evaluator,_,definitions=dataset_contract(name)
        report=EvaluationRunReport(dataset=name,dataset_version=version,evaluator=evaluator,status="FAILED",
            error_code=exc.code,run_id="unpublished",total_cases=len(definitions),passed_cases=0,failed_cases=0,
            created_at=started,completed_at=datetime.now(UTC))
        metadata["not_executed_cases"]=len(definitions)
    if source_identity(commit)["source_fingerprint"]!=source["source_fingerprint"]:
        raise EvaluationFixtureError("Source changed during evaluation; rerun against a consistent release.")
    if name not in DATASETS and report.status=="COMPLETED":
        _,_,_,definitions=dataset_contract(name)
        by_id={d.case_id:d for d in definitions}
        for case in report.cases:
            definition=by_id[case.case_id]
            case.fixture_id=definition.project_fixture
            case.evaluator_version=report.evaluator
            case.expected_output=dict(answer_type=definition.expected_answer_type,required_sources=definition.required_sources,
                expected_answer_terms=definition.expected_answer_terms,rubric=definition.rubric.model_dump())
            case.actual_output=dict(answer_type=case.answer_type,answer_text=case.answer_text,citation_labels=case.citation_labels)
            case.failure_reasons=[c.message for c in case.rubric_results.values() if not c.passed]
            case.references=["bundled:"+name+"/"+case.case_id]
    stable_cases=[c.model_dump(mode="json",exclude={"duration_ms"}) for c in report.cases]
    stable=dict(status=report.status,error_code=report.error_code,cases=stable_cases,metrics=report.aggregate_metrics)
    metadata["result_fingerprint"]=sha256(json.dumps(stable,sort_keys=True,allow_nan=False).encode()).hexdigest()
    metadata["report_fingerprint"]=sha256(report.model_dump_json().encode()).hexdigest()
    report.aggregate_metrics={**report.aggregate_metrics,"_publication":metadata}
    if session is not None:
        report.run_id,reused=persist_report(session,report,metadata,rerun=rerun)
        report.persisted=True
        # Reusing a saved run must return its original evidence, not today's timings.
        if reused:
            from app.db.repositories.evaluation_repository import EvaluationRepository
            repo=EvaluationRepository(session);row=repo.get_run(report.run_id)
            from app.schemas.evaluation import EvaluationCaseReport
            report.created_at=row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
            report.completed_at=row.completed_at if row.completed_at.tzinfo else row.completed_at.replace(tzinfo=UTC)
            report.aggregate_metrics=row.aggregate_metrics
            report.evaluation_details=row.aggregate_metrics.get("_evaluation",{})
            report.passed_cases=row.passed_cases;report.failed_cases=row.failed_cases;report.total_cases=row.total_cases
            report.skipped_cases=report.evaluation_details.get("skipped_cases",0)
            report.cases=[EvaluationCaseReport(**{**r.rubric_results["_evaluation"],"answer_text":r.answer_text or "",
                "rubric_results":{k:v for k,v in r.rubric_results.items() if k!="_evaluation"}}) for r in repo.list_results(row.id)]
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--dataset",choices=supported_datasets())
    selection.add_argument("--all",action="store_true")
    parser.add_argument("--publish",action="store_true",help="Explicitly write real results to the configured PostgreSQL target.")
    parser.add_argument("--database-name",help="Required target-name confirmation when publishing; never a connection string.")
    parser.add_argument("--source-commit",help="Full evaluated release commit; required when publishing.")
    parser.add_argument("--rerun",action="store_true",help="Publish a new run even if this release/dataset already has one.")
    parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args(argv)
    if args.publish:
        if not args.database_name or not args.source_commit:parser.error("Publishing requires --database-name and --source-commit.")
        from app.core.config import get_settings
        from sqlalchemy.engine import make_url
        try:
            url=get_settings().sqlalchemy_database_url()
            target=make_url(url) if url else None
        except Exception:parser.error("Configured PostgreSQL target is invalid.")
        if target is None:parser.error("Evaluation PostgreSQL persistence is not configured.")
        if target.get_backend_name()!="postgresql" or target.database!=args.database_name:
            parser.error("Configured PostgreSQL database does not match the confirmed target.")
    elif args.database_name or args.rerun:parser.error("Target confirmation and rerun apply only with --publish.")
    try:
        source_identity(args.source_commit)
        failed=False
        for name in supported_datasets() if args.all else (args.dataset,):
            if args.publish:
                from app.db.session import database_session
                with database_session() as session:report=evaluate_and_publish(name,session=session,commit=args.source_commit,rerun=args.rerun)
            else:report=evaluate_and_publish(name,commit=args.source_commit)
            if args.output_dir:
                args.output_dir.mkdir(parents=True,exist_ok=True)
                (args.output_dir/(name+".json")).write_text(report.model_dump_json(indent=2),encoding="utf-8")
            print(json.dumps(dict(dataset=name,run_id=report.run_id,status=report.status,passed=report.passed_cases,
                failed=report.failed_cases,skipped=report.skipped_cases,persisted=report.persisted,error_code=report.error_code)))
            failed=failed or report.status!="COMPLETED" or report.failed_cases>0
        return int(failed)
    except (ValueError,EvaluationFixtureError):
        print("Evaluation publication rejected: source, dataset or report validation failed.",file=sys.stderr);return 1
    except Exception:
        print("Evaluation publication failed; no partial run was committed for the failing dataset.",file=sys.stderr);return 1


if __name__=="__main__":raise SystemExit(main())
