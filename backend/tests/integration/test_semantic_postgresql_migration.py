"""Runtime PostgreSQL verification is restricted to the GitHub disposable localhost service."""
import os
from argparse import Namespace
from pathlib import Path
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_semantic_migration_on_disposable_postgresql():
    from app.core.config import get_settings
    settings=get_settings()
    url=settings.sqlalchemy_database_url(test=True)
    if os.environ.get('GITHUB_ACTIONS')!='true' or not url:
        pytest.skip('Disposable PostgreSQL runtime gate runs in GitHub Actions; no local PostgreSQL available.')
    parsed=make_url(url)
    if parsed.host not in {'localhost','127.0.0.1'} or parsed.database!='creatorlens_test' or url==settings.sqlalchemy_database_url():
        pytest.fail('Migration test refuses any non-disposable target.')
    root=Path(__file__).parents[2]
    config=Config(str(root/'alembic.ini'))
    config.set_main_option('script_location',str(root/'alembic'))
    config.cmd_opts=Namespace(x=['database=test'])
    command.upgrade(config,'head')
    engine=create_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()==ScriptDirectory.from_config(config).get_current_head()
            assert inspect(connection).has_table('semantic_snapshots')
    finally:
        engine.dispose()
