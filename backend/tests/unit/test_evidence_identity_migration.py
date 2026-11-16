"""Exercise the expansion against disposable SQLite and render PostgreSQL DDL offline."""
from importlib.util import spec_from_file_location, module_from_spec
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text, inspect


def migration():
    path = Path(__file__).parents[2] / "alembic/versions/20261111_0009_evidence_source_identity.py"
    spec = spec_from_file_location("evidence_identity_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expansion_preserves_unresolved_legacy_rows_and_is_reversible():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE metric_sources (id VARCHAR PRIMARY KEY, project_id VARCHAR, source_platform VARCHAR, metric_scope VARCHAR, source_method VARCHAR)"))
        connection.execute(text("CREATE TABLE evidence_chunks (id VARCHAR PRIMARY KEY)"))
        connection.execute(text("INSERT INTO metric_sources VALUES ('legacy', 'p', 'youtube', 'native', 'public_extractor')"))
        module = migration()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert connection.execute(text("SELECT slot, content_item_id FROM metric_sources WHERE id='legacy'")).one() == (None, None)
        connection.execute(text("INSERT INTO metric_sources (id,project_id,source_platform,metric_scope,source_method,slot) VALUES ('a','p','youtube','native','public_extractor','content_1'),('b','p','youtube','native','public_extractor','content_2')"))
        assert connection.execute(text("SELECT count(*) FROM metric_sources")).scalar() == 3
        assert "evidence_revision" in {c["name"] for c in inspect(connection).get_columns("evidence_chunks")}
        module.downgrade()
        assert "slot" not in {c["name"] for c in inspect(connection).get_columns("metric_sources")}
    engine.dispose()


def test_postgresql_expansion_ddl_is_renderable_without_database():
    output = StringIO()
    module = migration()
    module.op = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}))
    module.upgrade()
    sql = output.getvalue()
    assert "WHERE slot IS NOT NULL" in sql
    assert "evidence_revision" in sql
    assert "DELETE" not in sql and "UPDATE" not in sql
