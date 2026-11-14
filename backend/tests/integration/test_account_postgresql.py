"""Real concurrency gate; only the existing disposable GitHub PostgreSQL is allowed."""
import os
from pathlib import Path
from uuid import uuid4
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine,text,select,inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from fastapi import HTTPException


def test_disposable_account_migration_and_last_credit_race(monkeypatch):
    from app.core.config import get_settings
    settings=get_settings();url=settings.sqlalchemy_database_url(test=True)
    if os.environ.get("GITHUB_ACTIONS")!="true" or not url:pytest.skip("Disposable PostgreSQL ownership/concurrency gate runs in GitHub Actions; not executed locally.")
    parsed=make_url(url)
    if parsed.host not in {"localhost","127.0.0.1"} or parsed.database!="creatorlens_test" or url==settings.sqlalchemy_database_url():pytest.fail("Only the disposable test database is permitted.")
    schema="account_test_"+uuid4().hex
    engine=create_engine(url)
    root=Path(__file__).parents[2];config=Config(str(root/"alembic.ini"));config.set_main_option("script_location",str(root/"alembic"));config.cmd_opts=Namespace(x=["database=test"])
    try:
        with engine.begin() as connection:connection.execute(text("CREATE SCHEMA "+schema))
        with engine.connect() as connection:
            connection.execute(text("SET search_path TO "+schema));connection.commit();config.attributes["connection"]=connection
            command.upgrade(config,"20261113_0011")
            historical=str(uuid4())
            connection.execute(text("INSERT INTO projects (id,content_1_url,content_2_url,content_1_platform,content_2_platform,status,created_at,updated_at) VALUES (:id,'one','two','youtube','youtube','ready',now(),now())"),{"id":historical})
            from app.db.repositories.llm_run_repository import LlmRunRepository
            with Session(connection) as legacy:
                diagnostic=LlmRunRepository(legacy).start(project_id=None,llm_provider="gemini",llm_model="fixture",prompt_name="diagnostic_generation",prompt_version="1",operation_type="diagnostic_generation",execution_mode="offline_fixture",provider_invocation_count=0)
                diagnostic_id=diagnostic.id;legacy.commit()
            connection.commit();command.upgrade(config,"head")
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar()=="20261114_0013"
            assert connection.execute(text("SELECT owner_user_id FROM projects WHERE id=:id"),{"id":historical}).scalar() is None
            assert connection.execute(text("SELECT COUNT(*) FROM llm_runs WHERE id=:id AND project_id IS NULL"),{"id":diagnostic_id}).scalar()==1
            assert inspect(connection).has_table("semantic_snapshots") and inspect(connection).has_table("cost_events")
            columns={c["name"]:c for c in inspect(connection).get_columns("provider_operations")}
            assert all(columns[name]["nullable"] for name in ("operation_key","billing_pool","reserved_quantity","provider_details"))
            connection.commit()
        # Independent connections, same isolated schema; SQL row locks are genuinely exercised.
        from app.core.identity import Principal
        from app.core.access import provision,current_principal
        from app.db.models.account import UserEntitlement,AnalysisReservation,UsageEvent
        from app.db.repositories.project_repository import ProjectRepository
        from app.services.account_usage import reserve
        principal=Principal(str(uuid4()),str(uuid4()),1)
        scoped=create_engine(url,connect_args={"options":"-csearch_path="+schema})
        try:
            signup_barrier=Barrier(2)
            def signup(_):
                with Session(scoped) as session,session.begin():
                    signup_barrier.wait(timeout=10);provision(session,principal)
            with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(signup,[1,2]))
            with Session(scoped) as session,session.begin():
                provision(session,principal);ent=session.get(UserEntitlement,principal.user_id);ent.consumed=4
                handle=current_principal.set(principal)
                try:
                    project=ProjectRepository(session).create(project_id=str(uuid4()),content_1_url="one",content_2_url="two",content_1_platform="youtube",content_2_platform="youtube",status="created")["project_id"]
                finally:current_principal.reset(handle)
            barrier=Barrier(2)
            def attempt(i):
                try:
                    with Session(scoped) as session,session.begin():
                        barrier.wait(timeout=10)
                        value,_=reserve(session,principal,project,"concurrent-"+str(i))
                        return value.id
                except HTTPException as exc:return exc.status_code
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[1,2]))
            assert sum(isinstance(r,str) for r in results)==1 and 409 in results
            with Session(scoped) as session:
                value=session.get(UserEntitlement,principal.user_id)
                assert value.consumed==4 and value.reserved==1
                assert len(session.scalars(select(AnalysisReservation).where(AnalysisReservation.user_id==principal.user_id)).all())==1
                assert len(session.scalars(select(UsageEvent).where(UsageEvent.user_id==principal.user_id,UsageEvent.kind=="lifetime_grant")).all())==1
            _verify_extraction_admission_race(scoped,principal,project,monkeypatch)
        finally:scoped.dispose()
    finally:
        # The generated schema is verified before removing only isolated test resources.
        assert schema.startswith("account_test_") and len(schema)==45
        with engine.begin() as connection:connection.execute(text("DROP SCHEMA "+schema+" CASCADE"))
        engine.dispose()


def _verify_extraction_admission_race(engine,principal,project_id,monkeypatch):
    """Same slot delivered concurrently: one durable admission and one pool debit."""
    from datetime import date
    from decimal import Decimal
    from types import SimpleNamespace
    from app.db.models.account import AnalysisReservation,DispatchOutbox,ProviderOperation,BudgetAccount
    from app.db.models.project import Project
    from app.db.repositories.job_repository import JobRepository
    from app.extraction import accounting,policy
    s=SimpleNamespace(extraction_enabled=True,paid_operations_enabled=True,
        extraction_max_concurrent_operations=1,extraction_max_video_seconds=300,
        extraction_max_url_bytes=2048,extraction_max_response_bytes=16384,
        extraction_timeout_seconds=5,supadata_billing_tier="pro_monthly_prepaid",
        supadata_prepaid_verified=True,supadata_auto_recharge_disabled=True,
        supadata_api_key="offline-test-only",supadata_credit_pool="postgres-fixture-pool",
        supadata_credit_limit=1,supadata_transcript_mode="native",paid_requests_per_minute=1,
        provider_operation_ceiling_usd=".01",user_budget_usd="1",global_budget_usd="10")
    monkeypatch.setattr(accounting,"configuration",lambda settings:policy.configuration(settings,at=date(2026,11,14)))
    with Session(engine) as session,session.begin():
        project=session.get(Project,project_id)
        project.content_1_url="https://www.youtube.com/watch?v=bounded_one"
        project.content_2_url="https://www.youtube.com/watch?v=bounded_two"
        reservation=session.scalar(select(AnalysisReservation).where(AnalysisReservation.project_id==project_id))
        job=JobRepository(session).create(project_id);reservation.job_id=job.id
        session.add(DispatchOutbox(id=job.id,reservation_id=reservation.id,task_name="creatorlens.ingest_project",argument=job.id,state="claimed"))
    barrier=Barrier(2)
    def admit(_):
        try:
            with Session(engine) as session,session.begin():
                barrier.wait(timeout=10)
                return accounting.admit(session,principal,project_id,"content_1","https://www.youtube.com/watch?v=bounded_one","youtube","metadata",settings=s,rate=False)
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(admit,[1,2]))
    assert sum(isinstance(result,str) for result in results)==1 and 409 in results
    with Session(engine) as session:
        operations=session.scalars(select(ProviderOperation).where(ProviderOperation.project_id==project_id)).all()
        assert len(operations)==1 and operations[0].reserved_quantity==1
        assert operations[0].provider_details["estimated_cost_usd"]=="0.005666666667"
        assert operations[0].provider_details["actual_billed_cost_usd"] is None
        assert session.get(BudgetAccount,principal.user_id).reserved_usd==Decimal(".01")
        assert session.get(BudgetAccount,"global").reserved_usd==Decimal(".01")
        assert operations[0].operation_key is not None

    # Destructive contraction refuses to discard any newly recorded provider history.
    import importlib.util
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    path=Path(__file__).parents[2]/"alembic/versions/20261114_0013_extraction_accounting.py"
    spec=importlib.util.spec_from_file_location("extraction_revision",path)
    revision=importlib.util.module_from_spec(spec);spec.loader.exec_module(revision)
    with engine.connect() as connection,connection.begin():
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError,match="history"):
                revision.downgrade()
        assert connection.execute(text("SELECT COUNT(*) FROM provider_operations WHERE operation_key IS NOT NULL")).scalar()==1
