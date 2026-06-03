import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.core.paths import SQLITE_DB_PATH, STORAGE_DIR
from app.models.rag import RagChunk
from app.models.video import TranscriptSegment, VideoMetadata


def init_db() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                youtube_url TEXT,
                instagram_url TEXT,
                content_1_url TEXT,
                content_2_url TEXT,
                content_1_platform TEXT,
                content_2_platform TEXT,
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
                slot TEXT,
                platform TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                caption TEXT,
                creator TEXT,
                creator_handle TEXT,
                follower_count INTEGER,
                subscriber_count INTEGER,
                views INTEGER,
                likes INTEGER,
                comments INTEGER,
                reactions INTEGER,
                shares INTEGER,
                hashtags_json TEXT,
                upload_date TEXT,
                duration_seconds INTEGER,
                thumbnail_url TEXT,
                media_url TEXT,
                audio_url TEXT,
                engagement_rate REAL,
                missing_fields_json TEXT,
                transcript_available INTEGER NOT NULL DEFAULT 0,
                transcript_segment_count INTEGER NOT NULL DEFAULT 0,
                extraction_status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                metric_source_note TEXT,
                transcript_source_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, slot)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_segments (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                slot TEXT,
                platform TEXT NOT NULL,
                segment_index INTEGER NOT NULL,
                start_time REAL,
                end_time REAL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                content_id TEXT,
                slot TEXT,
                platform TEXT NOT NULL,
                source_type TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_time REAL,
                end_time REAL,
                title TEXT,
                creator TEXT,
                text TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                citation_label TEXT NOT NULL,
                qdrant_point_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_citations (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                platform TEXT,
                source_type TEXT,
                citation_label TEXT,
                text TEXT,
                score REAL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metric_sources (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                source_platform TEXT NOT NULL,
                source_method TEXT NOT NULL,
                metric_scope TEXT NOT NULL,
                url TEXT,
                views INTEGER,
                likes INTEGER,
                reactions INTEGER,
                comments INTEGER,
                shares INTEGER,
                followers INTEGER,
                engagement_rate REAL,
                confidence TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metric_sources_project_id "
            "ON metric_sources(project_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metric_sources_platform "
            "ON metric_sources(platform)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metric_sources_source_platform "
            "ON metric_sources(source_platform)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metric_sources_metric_scope "
            "ON metric_sources(metric_scope)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_metric_sources_source_method "
            "ON metric_sources(source_method)"
        )
        _ensure_project_columns(connection)
        _migrate_videos_table_for_slots(connection)
        _ensure_video_columns(connection)
        _ensure_transcript_columns(connection)
        _ensure_rag_chunk_columns(connection)
        connection.commit()


def create_project_record(
    project_id: str,
    status: str,
    youtube_url: str | None = None,
    instagram_url: str | None = None,
    content_1_url: str | None = None,
    content_2_url: str | None = None,
    content_1_platform: str | None = None,
    content_2_platform: str | None = None,
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
                content_1_url,
                content_2_url,
                content_1_platform,
                content_2_platform,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                youtube_url,
                instagram_url,
                content_1_url,
                content_2_url,
                content_1_platform,
                content_2_platform,
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
                COALESCE(content_1_url, youtube_url) AS content_1_url,
                COALESCE(content_2_url, instagram_url) AS content_2_url,
                COALESCE(content_1_platform, 'youtube') AS content_1_platform,
                COALESCE(content_2_platform, 'instagram') AS content_2_platform,
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
                COALESCE(content_1_url, youtube_url) AS content_1_url,
                COALESCE(content_2_url, instagram_url) AS content_2_url,
                COALESCE(content_1_platform, 'youtube') AS content_1_platform,
                COALESCE(content_2_platform, 'instagram') AS content_2_platform,
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
    slot: str | None = None,
) -> dict[str, Any]:
    init_db()
    content_slot = _content_slot(slot or metadata.slot or metadata.platform)
    existing = get_video_by_project_slot(project_id, content_slot)
    video_id = str(existing["id"]) if existing else str(uuid4())
    created_at = str(existing["created_at"]) if existing else _utc_timestamp()
    updated_at = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO videos (
                id,
                project_id,
                slot,
                platform,
                url,
                title,
                description,
                caption,
                creator,
                creator_handle,
                follower_count,
                subscriber_count,
                views,
                likes,
                comments,
                reactions,
                shares,
                hashtags_json,
                upload_date,
                duration_seconds,
                thumbnail_url,
                media_url,
                audio_url,
                engagement_rate,
                missing_fields_json,
                transcript_available,
                transcript_segment_count,
                extraction_status,
                error_message,
                metric_source_note,
                transcript_source_note,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, slot) DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                description = excluded.description,
                caption = excluded.caption,
                creator = excluded.creator,
                creator_handle = excluded.creator_handle,
                follower_count = excluded.follower_count,
                subscriber_count = excluded.subscriber_count,
                views = excluded.views,
                likes = excluded.likes,
                comments = excluded.comments,
                reactions = excluded.reactions,
                shares = excluded.shares,
                hashtags_json = excluded.hashtags_json,
                upload_date = excluded.upload_date,
                duration_seconds = excluded.duration_seconds,
                thumbnail_url = excluded.thumbnail_url,
                media_url = excluded.media_url,
                audio_url = excluded.audio_url,
                engagement_rate = excluded.engagement_rate,
                missing_fields_json = excluded.missing_fields_json,
                transcript_available = excluded.transcript_available,
                transcript_segment_count = excluded.transcript_segment_count,
                extraction_status = excluded.extraction_status,
                error_message = excluded.error_message,
                metric_source_note = excluded.metric_source_note,
                transcript_source_note = excluded.transcript_source_note,
                updated_at = excluded.updated_at
            """,
            (
                video_id,
                project_id,
                content_slot,
                metadata.platform,
                metadata.url,
                metadata.title,
                metadata.description,
                metadata.caption,
                metadata.creator,
                metadata.creator_handle,
                metadata.follower_count,
                metadata.subscriber_count,
                metadata.views,
                metadata.likes,
                metadata.comments,
                metadata.reactions,
                metadata.shares,
                json.dumps(metadata.hashtags),
                metadata.upload_date,
                metadata.duration_seconds,
                metadata.thumbnail_url,
                metadata.media_url,
                metadata.audio_url,
                metadata.engagement_rate,
                json.dumps(metadata.missing_fields),
                int(metadata.transcript_available),
                metadata.transcript_segment_count,
                metadata.extraction_status,
                metadata.error_message,
                metadata.metric_source_note,
                metadata.transcript_source_note,
                created_at,
                updated_at,
            ),
        )
        connection.commit()

    record = get_video_by_project_slot(project_id, content_slot)
    if record is None:
        raise RuntimeError("Video metadata record was not saved.")

    return record


def replace_transcript_segments(
    project_id: str,
    platform: str,
    video_id: str,
    segments: list[TranscriptSegment],
    slot: str | None = None,
) -> None:
    init_db()
    timestamp = _utc_timestamp()
    content_slot = _content_slot(slot or platform)

    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM transcript_segments
            WHERE project_id = ? AND slot = ?
            """,
            (project_id, content_slot),
        )
        connection.executemany(
            """
            INSERT INTO transcript_segments (
                id,
                video_id,
                project_id,
                slot,
                platform,
                segment_index,
                start_time,
                end_time,
                text,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid4()),
                    video_id,
                    project_id,
                    content_slot,
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
                slot,
                platform,
                url,
                title,
                description,
                caption,
                creator,
                creator_handle,
                follower_count,
                subscriber_count,
                views,
                likes,
                comments,
                reactions,
                shares,
                hashtags_json,
                upload_date,
                duration_seconds,
                thumbnail_url,
                media_url,
                audio_url,
                engagement_rate,
                missing_fields_json,
                transcript_available,
                transcript_segment_count,
                extraction_status,
                error_message,
                metric_source_note,
                transcript_source_note,
                created_at,
                updated_at
            FROM videos
            WHERE project_id = ? AND platform = ?
            ORDER BY
                CASE slot
                    WHEN 'content_1' THEN 0
                    WHEN 'content_2' THEN 1
                    ELSE 2
                END
            LIMIT 1
            """,
            (project_id, platform),
        ).fetchone()

    if row is None:
        return None

    return _video_row_to_dict(row)


def get_video_by_project_slot(
    project_id: str,
    slot: str,
) -> dict[str, Any] | None:
    init_db()
    content_slot = _content_slot(slot)

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                project_id,
                slot,
                platform,
                url,
                title,
                description,
                caption,
                creator,
                creator_handle,
                follower_count,
                subscriber_count,
                views,
                likes,
                comments,
                reactions,
                shares,
                hashtags_json,
                upload_date,
                duration_seconds,
                thumbnail_url,
                media_url,
                audio_url,
                engagement_rate,
                missing_fields_json,
                transcript_available,
                transcript_segment_count,
                extraction_status,
                error_message,
                metric_source_note,
                transcript_source_note,
                created_at,
                updated_at
            FROM videos
            WHERE project_id = ? AND slot = ?
            """,
            (project_id, content_slot),
        ).fetchone()

    if row is None:
        return None

    return _video_row_to_dict(row)


def list_video_records(project_id: str) -> list[dict[str, Any]]:
    init_db()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                project_id,
                slot,
                platform,
                url,
                title,
                description,
                caption,
                creator,
                creator_handle,
                follower_count,
                subscriber_count,
                views,
                likes,
                comments,
                reactions,
                shares,
                hashtags_json,
                upload_date,
                duration_seconds,
                thumbnail_url,
                media_url,
                audio_url,
                engagement_rate,
                missing_fields_json,
                transcript_available,
                transcript_segment_count,
                extraction_status,
                error_message,
                metric_source_note,
                transcript_source_note,
                created_at,
                updated_at
            FROM videos
            WHERE project_id = ?
            ORDER BY
                CASE slot
                    WHEN 'content_1' THEN 0
                    WHEN 'content_2' THEN 1
                    ELSE 2
                END,
                created_at ASC
            """,
            (project_id,),
        ).fetchall()

    return [_video_row_to_dict(row) for row in rows]


def get_transcript_preview(
    project_id: str,
    platform: str,
    limit: int = 10,
    slot: str | None = None,
) -> dict[str, Any] | None:
    init_db()

    if platform not in {"youtube", "instagram", "facebook"}:
        raise ValueError("Platform must be youtube, instagram, or facebook.")

    video = (
        get_video_by_project_slot(project_id, slot)
        if slot
        else get_video_by_project_platform(project_id, platform)
    )

    if video is None:
        return None

    safe_limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                segment_index,
                start_time,
                end_time,
                text
            FROM transcript_segments
            WHERE project_id = ? AND slot = ?
            ORDER BY segment_index ASC
            LIMIT ?
            """,
            (project_id, video["slot"], safe_limit),
        ).fetchall()

    segments = [
        TranscriptSegment(
            segment_index=row["segment_index"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            text=row["text"],
        )
        for row in rows
    ]

    return {
        "project_id": project_id,
        "slot": video["slot"],
        "platform": video["platform"],
        "transcript_available": video["transcript_available"],
        "transcript_segment_count": video["transcript_segment_count"],
        "segments": segments,
    }


def get_transcript_segments(
    project_id: str,
    platform: str,
    slot: str | None = None,
) -> list[dict[str, Any]]:
    init_db()

    if slot is None:
        video = get_video_by_project_platform(project_id, platform)
        content_slot = video["slot"] if video else platform
    else:
        content_slot = _content_slot(slot)

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                video_id,
                project_id,
                slot,
                platform,
                segment_index,
                start_time,
                end_time,
                text,
                created_at
            FROM transcript_segments
            WHERE project_id = ? AND slot = ?
            ORDER BY segment_index ASC
            """,
            (project_id, content_slot),
        ).fetchall()

    return [dict(row) for row in rows]


def replace_rag_chunks(project_id: str, chunks: list[RagChunk]) -> None:
    init_db()
    timestamp = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM rag_chunks
            WHERE project_id = ?
            """,
            (project_id,),
        )
        connection.executemany(
            """
            INSERT INTO rag_chunks (
                id,
                project_id,
                content_id,
                slot,
                platform,
                source_type,
                chunk_index,
                start_time,
                end_time,
                title,
                creator,
                text,
                content_hash,
                citation_label,
                qdrant_point_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.chunk_id,
                    chunk.project_id,
                    chunk.content_id,
                    chunk.slot,
                    chunk.platform,
                    chunk.source_type,
                    chunk.chunk_index,
                    chunk.start_time,
                    chunk.end_time,
                    chunk.title,
                    chunk.creator,
                    chunk.text,
                    chunk.content_hash,
                    chunk.citation_label,
                    chunk.qdrant_point_id,
                    timestamp,
                )
                for chunk in chunks
            ],
        )
        connection.commit()


def get_rag_chunks(
    project_id: str,
    platform: str | None = None,
) -> list[dict[str, Any]]:
    init_db()

    if platform is not None and platform not in {"youtube", "instagram", "facebook"}:
        raise ValueError("Platform must be youtube, instagram, or facebook.")

    query = """
        SELECT
            id AS chunk_id,
            project_id,
            content_id,
            slot,
            platform,
            source_type,
            chunk_index,
            start_time,
            end_time,
            title,
            creator,
            text,
            content_hash,
            citation_label,
            qdrant_point_id
        FROM rag_chunks
        WHERE project_id = ?
    """
    params: tuple[Any, ...]

    if platform is None:
        params = (project_id,)
    else:
        query += " AND platform = ?"
        params = (project_id, platform)

    query += """
        ORDER BY
            CASE slot
                WHEN 'content_1' THEN 0
                WHEN 'content_2' THEN 1
                ELSE 2
            END,
            CASE platform
                WHEN 'youtube' THEN 0
                WHEN 'instagram' THEN 1
                ELSE 2
            END,
            chunk_index ASC
    """

    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def update_rag_chunk_qdrant_point_id(
    chunk_id: str,
    qdrant_point_id: str,
) -> None:
    init_db()

    with _connect() as connection:
        connection.execute(
            """
            UPDATE rag_chunks
            SET qdrant_point_id = ?
            WHERE id = ?
            """,
            (qdrant_point_id, chunk_id),
        )
        connection.commit()


def create_chat_session(
    project_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    chat_session_id = session_id.strip() if isinstance(session_id, str) else ""
    chat_session_id = chat_session_id or str(uuid4())
    timestamp = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO chat_sessions (
                id,
                project_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                chat_session_id,
                project_id,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()

    record = get_chat_session(project_id=project_id, session_id=chat_session_id)
    if record is None:
        raise RuntimeError("Chat session record was not created.")

    return record


def get_chat_session(project_id: str, session_id: str) -> dict[str, Any] | None:
    init_db()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                id AS session_id,
                project_id,
                created_at,
                updated_at
            FROM chat_sessions
            WHERE project_id = ? AND id = ?
            """,
            (project_id, session_id),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


def save_chat_message(
    project_id: str,
    session_id: str,
    role: str,
    content: str,
) -> dict[str, Any]:
    init_db()
    message_id = str(uuid4())
    timestamp = _utc_timestamp()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO chat_messages (
                id,
                session_id,
                project_id,
                role,
                content,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                project_id,
                role,
                content,
                timestamp,
            ),
        )
        connection.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?
            WHERE project_id = ? AND id = ?
            """,
            (timestamp, project_id, session_id),
        )
        connection.commit()

    return {
        "message_id": message_id,
        "session_id": session_id,
        "project_id": project_id,
        "role": role,
        "content": content,
        "created_at": timestamp,
    }


def get_chat_messages(
    project_id: str,
    session_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    init_db()
    safe_limit = max(1, min(limit, 100))

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id AS message_id,
                session_id,
                project_id,
                role,
                content,
                created_at
            FROM chat_messages
            WHERE project_id = ? AND session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, session_id, safe_limit),
        ).fetchall()

    return [dict(row) for row in reversed(rows)]


def delete_chat_session(project_id: str, session_id: str) -> None:
    init_db()

    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM chat_citations
            WHERE project_id = ? AND session_id = ?
            """,
            (project_id, session_id),
        )
        connection.execute(
            """
            DELETE FROM chat_messages
            WHERE project_id = ? AND session_id = ?
            """,
            (project_id, session_id),
        )
        connection.execute(
            """
            DELETE FROM chat_sessions
            WHERE project_id = ? AND id = ?
            """,
            (project_id, session_id),
        )
        connection.commit()


def save_chat_citations(
    message_id: str,
    project_id: str,
    session_id: str,
    citations: list[dict[str, Any]],
) -> None:
    init_db()
    timestamp = _utc_timestamp()

    with _connect() as connection:
        connection.executemany(
            """
            INSERT INTO chat_citations (
                id,
                message_id,
                session_id,
                project_id,
                platform,
                source_type,
                citation_label,
                text,
                score,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(uuid4()),
                    message_id,
                    session_id,
                    project_id,
                    _optional_storage_text(citation.get("platform")),
                    _optional_storage_text(citation.get("source_type")),
                    _optional_storage_text(citation.get("citation_label")),
                    _optional_storage_text(citation.get("text")),
                    _optional_storage_float(citation.get("score")),
                    timestamp,
                )
                for citation in citations
            ],
        )
        connection.commit()


def upsert_metric_source_record(
    project_id: str,
    platform: str,
    source_platform: str,
    source_method: str,
    metric_scope: str,
    url: str | None = None,
    views: int | None = None,
    likes: int | None = None,
    reactions: int | None = None,
    comments: int | None = None,
    shares: int | None = None,
    followers: int | None = None,
    engagement_rate: float | None = None,
    confidence: str = "medium",
    note: str | None = None,
    record_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    timestamp = _utc_timestamp()

    existing = None
    if record_id is None:
        existing = get_latest_metric_source(
            project_id=project_id,
            source_platform=source_platform,
            metric_scope=metric_scope,
            source_method=source_method,
        )

    metric_source_id = record_id or (
        str(existing["id"]) if existing is not None else str(uuid4())
    )
    created_at = (
        str(existing["created_at"])
        if existing is not None and existing.get("created_at")
        else timestamp
    )

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO metric_sources (
                id,
                project_id,
                platform,
                source_platform,
                source_method,
                metric_scope,
                url,
                views,
                likes,
                reactions,
                comments,
                shares,
                followers,
                engagement_rate,
                confidence,
                note,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                platform = excluded.platform,
                source_platform = excluded.source_platform,
                source_method = excluded.source_method,
                metric_scope = excluded.metric_scope,
                url = excluded.url,
                views = excluded.views,
                likes = excluded.likes,
                reactions = excluded.reactions,
                comments = excluded.comments,
                shares = excluded.shares,
                followers = excluded.followers,
                engagement_rate = excluded.engagement_rate,
                confidence = excluded.confidence,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                metric_source_id,
                project_id,
                platform,
                source_platform,
                source_method,
                metric_scope,
                url,
                views,
                likes,
                reactions,
                comments,
                shares,
                followers,
                engagement_rate,
                confidence,
                note,
                created_at,
                timestamp,
            ),
        )
        connection.commit()

    record = get_metric_source_record(
        project_id=project_id,
        record_id=metric_source_id,
    )
    if record is None:
        raise RuntimeError("Metric source record was not saved.")

    return record


def get_metric_source_record(
    project_id: str,
    record_id: str,
) -> dict[str, Any] | None:
    init_db()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                project_id,
                platform,
                source_platform,
                source_method,
                metric_scope,
                url,
                views,
                likes,
                reactions,
                comments,
                shares,
                followers,
                engagement_rate,
                confidence,
                note,
                created_at,
                updated_at
            FROM metric_sources
            WHERE project_id = ? AND id = ?
            """,
            (project_id, record_id),
        ).fetchone()

    return dict(row) if row is not None else None


def list_metric_source_records(project_id: str) -> list[dict[str, Any]]:
    init_db()

    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                project_id,
                platform,
                source_platform,
                source_method,
                metric_scope,
                url,
                views,
                likes,
                reactions,
                comments,
                shares,
                followers,
                engagement_rate,
                confidence,
                note,
                created_at,
                updated_at
            FROM metric_sources
            WHERE project_id = ?
            ORDER BY updated_at DESC
            """,
            (project_id,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_latest_metric_source(
    project_id: str,
    source_platform: str,
    metric_scope: str,
    source_method: str | None = None,
) -> dict[str, Any] | None:
    init_db()
    query = """
        SELECT
            id,
            project_id,
            platform,
            source_platform,
            source_method,
            metric_scope,
            url,
            views,
            likes,
            reactions,
            comments,
            shares,
            followers,
            engagement_rate,
            confidence,
            note,
            created_at,
            updated_at
        FROM metric_sources
        WHERE project_id = ? AND source_platform = ? AND metric_scope = ?
    """
    params: tuple[Any, ...]

    if source_method is None:
        params = (project_id, source_platform, metric_scope)
    else:
        query += " AND source_method = ?"
        params = (project_id, source_platform, metric_scope, source_method)

    query += " ORDER BY updated_at DESC LIMIT 1"

    with _connect() as connection:
        row = connection.execute(query, params).fetchone()

    return dict(row) if row is not None else None


def delete_metric_source_record(project_id: str, record_id: str) -> None:
    init_db()

    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM metric_sources
            WHERE project_id = ? AND id = ?
            """,
            (project_id, record_id),
        )
        connection.commit()


def get_project_detail_record(project_id: str) -> dict[str, Any] | None:
    project = get_project_record(project_id)

    if project is None:
        return None

    content_items = [
        _metadata_from_video_record(record)
        for record in list_video_records(project_id)
    ]
    project["content_items"] = [
        item for item in content_items if item is not None
    ]
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


def _optional_storage_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _optional_storage_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _video_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["hashtags"] = json.loads(record.pop("hashtags_json") or "[]")
    record["missing_fields"] = json.loads(record.pop("missing_fields_json") or "[]")
    record["transcript_available"] = bool(record["transcript_available"])
    return record


def _metadata_from_video_record(
    record: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if record is None:
        return None

    return {
        "id": record["id"],
        "content_id": record["id"],
        "slot": record["slot"],
        "platform": record["platform"],
        "url": record["url"],
        "title": record["title"],
        "description": record["description"],
        "caption": record["caption"],
        "creator": record["creator"],
        "creator_handle": record["creator_handle"],
        "follower_count": record["follower_count"],
        "subscriber_count": record["subscriber_count"],
        "views": record["views"],
        "likes": record["likes"],
        "comments": record["comments"],
        "reactions": record["reactions"],
        "shares": record["shares"],
        "hashtags": record["hashtags"],
        "upload_date": record["upload_date"],
        "duration_seconds": record["duration_seconds"],
        "thumbnail_url": record["thumbnail_url"],
        "media_url": record["media_url"],
        "audio_url": record["audio_url"],
        "engagement_rate": record["engagement_rate"],
        "missing_fields": record["missing_fields"],
        "transcript_available": record["transcript_available"],
        "transcript_segment_count": record["transcript_segment_count"],
        "extraction_status": record["extraction_status"],
        "error_message": record["error_message"],
        "metric_source_note": record["metric_source_note"],
        "transcript_source_note": record["transcript_source_note"],
    }


def _ensure_video_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(videos)").fetchall()
    }
    required_columns = {
        "slot": "TEXT",
        "description": "TEXT",
        "caption": "TEXT",
        "creator_handle": "TEXT",
        "subscriber_count": "INTEGER",
        "reactions": "INTEGER",
        "shares": "INTEGER",
        "thumbnail_url": "TEXT",
        "media_url": "TEXT",
        "audio_url": "TEXT",
        "missing_fields_json": "TEXT",
        "metric_source_note": "TEXT",
        "transcript_source_note": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if column_name in existing_columns:
            continue

        connection.execute(
            f"ALTER TABLE videos ADD COLUMN {column_name} {column_type}"
        )


def _ensure_project_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(projects)").fetchall()
    }
    required_columns = {
        "content_1_url": "TEXT",
        "content_2_url": "TEXT",
        "content_1_platform": "TEXT",
        "content_2_platform": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if column_name in existing_columns:
            continue

        connection.execute(
            f"ALTER TABLE projects ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        """
        UPDATE projects
        SET
            content_1_url = COALESCE(content_1_url, youtube_url),
            content_2_url = COALESCE(content_2_url, instagram_url),
            content_1_platform = COALESCE(content_1_platform, 'youtube'),
            content_2_platform = COALESCE(content_2_platform, 'instagram')
        """
    )


def _ensure_transcript_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(transcript_segments)").fetchall()
    }

    if "slot" not in existing_columns:
        connection.execute("ALTER TABLE transcript_segments ADD COLUMN slot TEXT")

    connection.execute(
        """
        UPDATE transcript_segments
        SET slot = COALESCE(
            slot,
            CASE platform
                WHEN 'youtube' THEN 'content_1'
                WHEN 'instagram' THEN 'content_2'
                ELSE platform
            END
        )
        """
    )


def _ensure_rag_chunk_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(rag_chunks)").fetchall()
    }

    required_columns = {
        "content_id": "TEXT",
        "slot": "TEXT",
    }

    for column_name, column_type in required_columns.items():
        if column_name in existing_columns:
            continue

        connection.execute(
            f"ALTER TABLE rag_chunks ADD COLUMN {column_name} {column_type}"
        )

    connection.execute(
        """
        UPDATE rag_chunks
        SET slot = COALESCE(
            slot,
            CASE platform
                WHEN 'youtube' THEN 'content_1'
                WHEN 'instagram' THEN 'content_2'
                ELSE platform
            END
        )
        """
    )


def _migrate_videos_table_for_slots(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'videos'
        """
    ).fetchone()
    table_sql = str(row["sql"]) if row and row["sql"] else ""

    if "UNIQUE(project_id, platform)" not in table_sql:
        return

    connection.execute("ALTER TABLE videos RENAME TO videos_legacy_platform_unique")
    connection.execute(
        """
        CREATE TABLE videos (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            slot TEXT,
            platform TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            description TEXT,
            caption TEXT,
            creator TEXT,
            creator_handle TEXT,
            follower_count INTEGER,
            subscriber_count INTEGER,
            views INTEGER,
            likes INTEGER,
            comments INTEGER,
            reactions INTEGER,
            shares INTEGER,
            hashtags_json TEXT,
            upload_date TEXT,
            duration_seconds INTEGER,
            thumbnail_url TEXT,
            media_url TEXT,
            audio_url TEXT,
            engagement_rate REAL,
            missing_fields_json TEXT,
            transcript_available INTEGER NOT NULL DEFAULT 0,
            transcript_segment_count INTEGER NOT NULL DEFAULT 0,
            extraction_status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            metric_source_note TEXT,
            transcript_source_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, slot)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO videos (
            id,
            project_id,
            slot,
            platform,
            url,
            title,
            description,
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
            metric_source_note,
            transcript_source_note,
            created_at,
            updated_at
        )
        SELECT
            id,
            project_id,
            CASE platform
                WHEN 'youtube' THEN 'content_1'
                WHEN 'instagram' THEN 'content_2'
                ELSE platform
            END,
            platform,
            url,
            title,
            description,
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
            metric_source_note,
            transcript_source_note,
            created_at,
            updated_at
        FROM videos_legacy_platform_unique
        """
    )


def _content_slot(slot: str) -> str:
    clean_slot = slot.strip() if isinstance(slot, str) else ""

    if clean_slot in {"content_1", "content_2"}:
        return clean_slot

    if clean_slot == "youtube":
        return "content_1"

    if clean_slot == "instagram":
        return "content_2"

    return clean_slot or "content_1"
