import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.core.paths import SQLITE_DB_PATH, STORAGE_DIR


def init_db() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                youtube_url TEXT NOT NULL,
                instagram_url TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def create_project_record(
    project_id: str,
    youtube_url: str,
    instagram_url: str,
    status: str,
) -> dict[str, Any]:
    init_db()
    timestamp = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO projects (
                id,
                youtube_url,
                instagram_url,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                youtube_url,
                instagram_url,
                status,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()

    record = get_project_record(project_id)
    if record is None:
        raise RuntimeError("Project record was not created.")

    return record


def get_project_record(project_id: str) -> dict[str, Any] | None:
    init_db()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                id AS project_id,
                youtube_url,
                instagram_url,
                status,
                created_at,
                updated_at
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def list_project_records(limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    safe_limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id AS project_id,
                youtube_url,
                instagram_url,
                status,
                created_at,
                updated_at
            FROM projects
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()
