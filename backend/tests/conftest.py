from copy import deepcopy
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
import app.db.models  # noqa: F401


FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures"


@pytest.fixture
def comparison_project_fixture() -> dict[str, object]:
    fixture_path = FIXTURE_DIRECTORY / "comparison_project.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return deepcopy(payload)


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def block_external_provider_network(monkeypatch):
    """Normal tests cannot reach external Python HTTP providers; disposable DBs remain loopback-only."""
    import socket
    connect = socket.socket.connect
    resolve = socket.getaddrinfo
    allowed = {'localhost', '127.0.0.1', '::1', None}
    def safe_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in allowed:
            raise RuntimeError('Tests prohibit external provider connections.')
        return connect(sock, address)
    def safe_resolve(host, *args, **kwargs):
        if host not in allowed:
            raise RuntimeError('Tests prohibit external provider DNS resolution.')
        return resolve(host, *args, **kwargs)
    monkeypatch.setattr(socket.socket, 'connect', safe_connect)
    monkeypatch.setattr(socket, 'getaddrinfo', safe_resolve)
