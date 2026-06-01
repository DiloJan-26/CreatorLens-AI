import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.paths import SQLITE_DB_PATH, STORAGE_DIR
from app.models.video import TranscriptSegment, VideoMetadata


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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                creator TEXT,
                follower_count INTEGER,
                views INTEGER,
                likes INTEGER,
                comments INTEGER,
                hashtags_json TEXT,
                upload_date TEXT,
                duration_seconds INTEGER,
                engagement_rate REAL,
                transcript_available INTEGER NOT NULL DEFAULT 0,
                transcript_segment_count INTEGER NOT NULL DEFAULT 0,
                extraction_status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, platform)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_segments (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                segment_index INTEGER NOT NULL,
                start_time REAL,
                end_time REAL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
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


def update_project_status(project_id: str, status: str) -> None:
    init_db()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE projects
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, _utc_timestamp(), project_id),
        )
        connection.commit()


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


def upsert_video_metadata(
    project_id: str,
    metadata: VideoMetadata,
) -> dict[str, Any]:
    init_db()
    existing = get_video_by_project_platform(project_id, metadata.platform)
    video_id = str(existing["id"]) if existing else str(uuid4())
    created_at = str(existing["created_at"]) if existing else _utc_timestamp()
    updated_at = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO videos (
                id,
                project_id,
                platform,
                url,
                title,
                creator,
                follower_count,
                views,
                likes,
                comments,
                hashtags_json,
                upload_date,
                duration_seconds,
                engagement_rate,
                transcript_available,
                transcript_segment_count,
                extraction_status,
                error_message,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, platform) DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                creator = excluded.creator,
                follower_count = excluded.follower_count,
                views = excluded.views,
                likes = excluded.likes,
                comments = excluded.comments,
                hashtags_json = excluded.hashtags_json,
                upload_date = excluded.upload_date,
                duration_seconds = excluded.duration_seconds,
                engagement_rate = excluded.engagement_rate,
                transcript_available = excluded.transcript_available,
                transcript_segment_count = excluded.transcript_segment_count,
                extraction_status = excluded.extraction_status,
                error_message = excluded.error_message,
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                project_id,
                metadata.platform,
                metadata.url,
                metadata.title,
                metadata.creator,
                metadata.follower_count,
                metadata.views,
                metadata.likes,
                metadata.comments,
                json.dumps(metadata.hashtags),
                metadata.upload_date,
                metadata.duration_seconds,
                metadata.engagement_rate,
                int(metadata.transcript_available),
                metadata.transcript_segment_count,
                metadata.extraction_status,
                metadata.error_message,
                created_at,
                updated_at,
            ),
        )
        connection.commit()

    record = get_video_by_project_platform(project_id, metadata.platform)
    if record is None:
        raise RuntimeError("Video metadata record was not saved.")

    return record


def replace_transcript_segments(
    project_id: str,
    platform: str,
    video_id: str,
    segments: list[TranscriptSegment],
) -> None:
    init_db()
    timestamp = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM transcript_segments
            WHERE project_id = ? AND platform = ?
            """,
            (project_id, platform),
        )
        connection.executemany(
            """
            INSERT INTO transcript_segments (
                id,
                video_id,
                project_id,
                platform,
                segment_index,
                start_time,
                end_time,
                text,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid4()),
                    video_id,
                    project_id,
                    platform,
                    segment.segment_index,
                    segment.start_time,
                    segment.end_time,
                    segment.text,
                    timestamp,
                )
                for segment in segments
            ],
        )
        connection.execute(
            """
            UPDATE videos
            SET
                transcript_available = ?,
                transcript_segment_count = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (int(bool(segments)), len(segments), timestamp, video_id),
        )
        connection.commit()


def get_video_by_project_platform(
    project_id: str,
    platform: str,
) -> dict[str, Any] | None:
    init_db()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                project_id,
                platform,
                url,
                title,
                creator,
                follower_count,
                views,
                likes,
                comments,
                hashtags_json,
                upload_date,
                duration_seconds,
                engagement_rate,
                transcript_available,
                transcript_segment_count,
                extraction_status,
                error_message,
                created_at,
                updated_at
            FROM videos
            WHERE project_id = ? AND platform = ?
            """,
            (project_id, platform),
        ).fetchone()

    if row is None:
        return None

    return _video_row_to_dict(row)


def get_transcript_segments(project_id: str, platform: str) -> list[dict[str, Any]]:
    init_db()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                video_id,
                project_id,
                platform,
                segment_index,
                start_time,
                end_time,
                text,
                created_at
            FROM transcript_segments
            WHERE project_id = ? AND platform = ?
            ORDER BY segment_index ASC
            """,
            (project_id, platform),
        ).fetchall()

    return [dict(row) for row in rows]


def get_project_detail_record(project_id: str) -> dict[str, Any] | None:
    project = get_project_record(project_id)

    if project is None:
        return None

    project["youtube"] = _metadata_from_video_record(
        get_video_by_project_platform(project_id, "youtube")
    )
    project["instagram"] = _metadata_from_video_record(
        get_video_by_project_platform(project_id, "instagram")
    )

    return project


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _video_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["hashtags"] = json.loads(record.pop("hashtags_json") or "[]")
    record["transcript_available"] = bool(record["transcript_available"])
    return record


def _metadata_from_video_record(
    record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if record is None:
        return None

    return {
        "platform": record["platform"],
        "url": record["url"],
        "title": record["title"],
        "creator": record["creator"],
        "follower_count": record["follower_count"],
        "views": record["views"],
        "likes": record["likes"],
        "comments": record["comments"],
        "hashtags": record["hashtags"],
        "upload_date": record["upload_date"],
        "duration_seconds": record["duration_seconds"],
        "engagement_rate": record["engagement_rate"],
        "transcript_available": record["transcript_available"],
        "transcript_segment_count": record["transcript_segment_count"],
        "extraction_status": record["extraction_status"],
        "error_message": record["error_message"],
    }
