"""Local disposable SQLite compatibility and guarded GitHub PostgreSQL verification."""
from contextlib import contextmanager
from pathlib import Path
import importlib.util
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.config import Config
from alembic import command
from app.db.repositories.cost_repository import CostRepository
from app.llm.operation_analytics import operation_analytics
from tests.unit.test_content_item_repository import _create_project
from tests.unit.test_operation_observability import record


def revision():
    path=Path(__file__).parents[2]/'alembic/versions/20261113_0011_add_operation_telemetry.py'
    spec=importlib.util.spec_from_file_location('operation_telemetry_revision',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def test_operation_telemetry_api_scope_pagination_history_and_no_inference(db_session,monkeypatch):
    from app.services import llm_observability_service as service
    from app.api import metrics
    from decimal import Decimal
    project=_create_project(db_session)
    record(db_session,project,cost=Decimal('.0044059'));record(db_session,project,det=True);record(db_session,project)
    @contextmanager
    def session():yield db_session
    monkeypatch.setattr(service,'database_session',session)
    monkeypatch.setattr(service,'is_database_configured',lambda:True)
    app=FastAPI();app.include_router(metrics.cost_router)
    with TestClient(app) as client:
        response=client.get('/api/metrics/cost',params={'project_id':project,'limit':1})
    assert response.status_code==200
    data=response.json()
    assert len(data['runs'])==1 and data['totals']['total_operations']==3
    assert data['totals']['model_invocations']==2 and data['totals']['cost_status']=='partial'
    assert data['totals']['estimated_cost_usd'] is None
    assert data['analytics']['latencies']['gemini_inference']['samples']==2
    assert data['totals']['actual_billed_cost_usd'] is None


def test_operation_telemetry_additive_upgrade_downgrade_preserves_legacy_rows(db_session):
    from decimal import Decimal
    project=_create_project(db_session);run=record(db_session,project,cost=Decimal('.0044059'))
    connection=db_session.connection()
    with Operations.context(MigrationContext.configure(connection)):
        revision().downgrade()
        assert 'telemetry' not in {c['name'] for c in inspect(connection).get_columns('llm_runs')}
        assert connection.execute(text('SELECT COUNT(*) FROM llm_runs WHERE id=:id'),{'id':run.id}).scalar()==1
        revision().upgrade()
    db_session.expire_all()
    assert CostRepository(db_session).summary(project_id=project)['estimated_cost_usd']==Decimal('.0044059')
    assert 'telemetry' in {c['name'] for c in inspect(connection).get_columns('llm_runs')}


def test_operation_telemetry_postgresql_migration_and_aggregates():
    from app.core.config import get_settings
    settings=get_settings();url=settings.sqlalchemy_database_url(test=True)
    if os.environ.get('GITHUB_ACTIONS')!='true' or not url:
        pytest.skip('Disposable PostgreSQL upgrade/downgrade and aggregation gate runs in GitHub Actions.')
    target=make_url(url)
    if target.host not in {'localhost','127.0.0.1'} or target.database!='creatorlens_test' or url==settings.sqlalchemy_database_url():
        pytest.fail('Only the disposable GitHub PostgreSQL test database is permitted.')
    from argparse import Namespace
    root=Path(__file__).parents[2];config=Config(str(root/'alembic.ini'));config.set_main_option('script_location',str(root/'alembic'))
    config.cmd_opts=Namespace(x=['database=test']);command.upgrade(config,'head')
    engine=create_engine(url)
    try:
        with engine.connect() as connection,connection.begin():
            with Session(bind=connection,join_transaction_mode='create_savepoint') as session:
                project=_create_project(session);record(session,project);record(session,project,det=True)
                assert CostRepository(session).summary(project_id=project)['estimated_cost_usd'] is None
                assert operation_analytics(session,project)['latencies']['gemini_inference']['mean_ms']==9320
                assert next(c for c in inspect(connection).get_columns('llm_runs') if c['name']=='project_id')['nullable'] is True
                from app.db.repositories.llm_run_repository import LlmRunRepository
                with session.begin_nested() as diagnostic_fixture:
                    diagnostic=LlmRunRepository(session).start(project_id=None,llm_provider='gemini',llm_model='fixture',
                        prompt_name='diagnostic_generation',prompt_version='1',operation_type='diagnostic_generation',execution_mode='runtime',provider_invocation_count=1)
                    CostRepository(session).record(llm_run_id=diagnostic.id,project_id=None,llm_provider='gemini',llm_model='fixture',usage=None,estimated_cost_usd=None)
                    with Operations.context(MigrationContext.configure(connection)):
                        with pytest.raises(RuntimeError):revision().downgrade()
                    diagnostic_fixture.rollback()
                with session.begin_nested() as precision_fixture:
                    from app.llm.cost_estimation import estimate_model_cost
                    from app.llm.token_usage import parse_token_usage
                    from datetime import date
                    tiny_project = _create_project(session)
                    tiny_run = record(session, tiny_project)
                    cached = parse_token_usage({'usage_metadata': {'input_tokens': 1, 'output_tokens': 0,
                        'input_token_details': {'cache_read': 1}}})
                    estimate = estimate_model_cost(cached, provider='gemini', model='gemini-3.6-flash',
                        service_tier='standard', at=date(2026, 12, 31), caching_mode='implicit')
                    costs = CostRepository(session)
                    costs.record(llm_run_id=tiny_run.id, project_id=tiny_project, llm_provider='gemini',
                        llm_model='gemini-3.6-flash', usage=cached, estimated_cost_usd=estimate['estimated_cost_usd'],
                        estimate_details=estimate, event_key='disposable-cached-token')
                    assert costs.summary(project_id=tiny_project)['priced_subtotal_usd'] == Decimal('.000000075')
                    assert Decimal(operation_analytics(session, tiny_project)['daily'][0]['priced_subtotal_usd']) == Decimal('.000000075')
                    precision_fixture.rollback()
                with Operations.context(MigrationContext.configure(connection)):
                    revision().downgrade();revision().upgrade()
                session.expire_all()
                assert CostRepository(session).summary(project_id=project)['event_count']==2
    finally:engine.dispose()
