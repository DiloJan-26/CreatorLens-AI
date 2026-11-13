"""Transactional claim and immutable successful result persistence."""
from contextlib import contextmanager
from datetime import datetime, UTC
from sqlalchemy import create_engine, inspect, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models.semantic_snapshot import SemanticSnapshot
from app.db.session import database_session, is_database_configured

@contextmanager
def semantic_session(*, create=False):
    if is_database_configured():
        with database_session() as session:
            yield session
        return
    from app.core import paths
    engine = create_engine("sqlite+pysqlite:///" + str(paths.SQLITE_DB_PATH))
    try:
        if create:
            paths.SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            SemanticSnapshot.__table__.create(engine, checkfirst=True)
        elif not paths.SQLITE_DB_PATH.exists() or not inspect(engine).has_table("semantic_snapshots"):
            yield None
            return
        with Session(engine, expire_on_commit=False) as session:
            with session.begin():
                yield session
    finally:
        engine.dispose()


def snapshot_record(row):
    if row is None:
        return None
    return {column.name: getattr(row, column.name) for column in SemanticSnapshot.__table__.columns}


def read_snapshot(key):
    with semantic_session() as session:
        return snapshot_record(session.get(SemanticSnapshot, key)) if session else None


def create_pending(*, key, context, model_id, prompt_version, schema_version):
    now = datetime.now(UTC)
    try:
        with semantic_session(create=True) as session:
            row = SemanticSnapshot(id=key, project_id=context['project_id'], content_id=context['content_id'], slot=context['slot'],
                status='pending', attempts=0, context=context, result=None, processing={}, model_id=model_id,
                prompt_version=prompt_version, schema_version=schema_version, created_at=now, updated_at=now)
            session.add(row)
            session.flush()
        return True
    except IntegrityError:
        # The primary key resolves simultaneous requests; caller reads the winner.
        return False


def transition(key, expected, target, *, attempt=None, **values):
    with semantic_session(create=True) as session:
        statement = update(SemanticSnapshot).where(SemanticSnapshot.id == key, SemanticSnapshot.status == expected)
        if attempt is not None:
            statement = statement.where(SemanticSnapshot.attempts == attempt)
        changed = session.execute(statement.values(status=target, updated_at=datetime.now(UTC), **values)).rowcount
        return bool(changed)


def claim_snapshot(key):
    with semantic_session(create=True) as session:
        changed = session.execute(update(SemanticSnapshot).where(SemanticSnapshot.id == key,
            SemanticSnapshot.status == 'pending', SemanticSnapshot.attempts < 2)
            .values(status='running', attempts=SemanticSnapshot.attempts + 1, updated_at=datetime.now(UTC))).rowcount
        return bool(changed)
