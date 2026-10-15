from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class IngestionJobStatus(StrEnum):
    PENDING = "PENDING"
    EXTRACTING_METADATA = "EXTRACTING_METADATA"
    EXTRACTING_TRANSCRIPT = "EXTRACTING_TRANSCRIPT"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    READY = "READY"
    PARTIAL_READY = "PARTIAL_READY"
    FAILED = "FAILED"


TERMINAL_JOB_STATUSES = frozenset(
    {
        IngestionJobStatus.READY,
        IngestionJobStatus.PARTIAL_READY,
        IngestionJobStatus.FAILED,
    }
)

ALLOWED_JOB_TRANSITIONS: dict[
    IngestionJobStatus,
    frozenset[IngestionJobStatus],
] = {
    IngestionJobStatus.PENDING: frozenset(
        {IngestionJobStatus.EXTRACTING_METADATA, IngestionJobStatus.FAILED}
    ),
    IngestionJobStatus.EXTRACTING_METADATA: frozenset(
        {IngestionJobStatus.EXTRACTING_TRANSCRIPT, IngestionJobStatus.FAILED}
    ),
    IngestionJobStatus.EXTRACTING_TRANSCRIPT: frozenset(
        {IngestionJobStatus.CHUNKING, IngestionJobStatus.FAILED}
    ),
    IngestionJobStatus.CHUNKING: frozenset(
        {IngestionJobStatus.EMBEDDING, IngestionJobStatus.FAILED}
    ),
    IngestionJobStatus.EMBEDDING: frozenset(
        {IngestionJobStatus.INDEXING, IngestionJobStatus.FAILED}
    ),
    IngestionJobStatus.INDEXING: frozenset(
        {
            IngestionJobStatus.READY,
            IngestionJobStatus.PARTIAL_READY,
            IngestionJobStatus.FAILED,
        }
    ),
    IngestionJobStatus.READY: frozenset(),
    IngestionJobStatus.PARTIAL_READY: frozenset(),
    IngestionJobStatus.FAILED: frozenset(),
}

JOB_PROGRESS_PERCENT = {
    IngestionJobStatus.PENDING: 0,
    IngestionJobStatus.EXTRACTING_METADATA: 15,
    IngestionJobStatus.EXTRACTING_TRANSCRIPT: 35,
    IngestionJobStatus.CHUNKING: 55,
    IngestionJobStatus.EMBEDDING: 70,
    IngestionJobStatus.INDEXING: 85,
    IngestionJobStatus.READY: 100,
    IngestionJobStatus.PARTIAL_READY: 100,
    IngestionJobStatus.FAILED: 100,
}


def can_transition_job(
    current: IngestionJobStatus,
    target: IngestionJobStatus,
) -> bool:
    return current == target or target in ALLOWED_JOB_TRANSITIONS[current]


class IngestionStartResponse(BaseModel):
    project_id: str
    job_id: str
    status: IngestionJobStatus
    status_url: str
    message: str


class IngestionStatusResponse(BaseModel):
    project_id: str
    job_id: str
    status: IngestionJobStatus
    progress_percent: int = Field(ge=0, le=100)
    retry_count: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

