"""Exercise semantic table expansion on disposable SQLite and render PostgreSQL DDL."""
from importlib.util import spec_from_file_location, module_from_spec
from io import StringIO
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text, inspect

def migration():
    path=Path(__file__).parents[2]/'alembic/versions/20261113_0010_semantic_snapshots.py'
    spec=spec_from_file_location('semantic_migration',path)
    module=module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_semantic_migration_preserves_existing_tables_and_reverses():
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE existing_data (id INTEGER PRIMARY KEY)'))
        connection.execute(text('INSERT INTO existing_data VALUES (1)'))
        module=migration();module.op=Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert inspect(connection).has_table('semantic_snapshots')
        assert connection.execute(text('SELECT id FROM existing_data')).scalar()==1
        module.downgrade()
        assert not inspect(connection).has_table('semantic_snapshots')
    engine.dispose()

def test_semantic_migration_postgresql_sql_offline():
    output=StringIO();module=migration()
    module.op=Operations(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':output}))
    module.upgrade();sql=output.getvalue()
    assert 'PRIMARY KEY (id)' in sql and 'semantic_snapshots' in sql
    assert 'DELETE' not in sql and 'UPDATE' not in sql
