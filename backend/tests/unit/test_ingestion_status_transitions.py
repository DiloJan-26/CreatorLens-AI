from itertools import pairwise

import pytest

from app.schemas.ingestion import IngestionJobStatus, can_transition_job


def test_ingestion_happy_path_transitions_are_allowed() -> None:
    states = [
        IngestionJobStatus.PENDING,
        IngestionJobStatus.EXTRACTING_METADATA,
        IngestionJobStatus.EXTRACTING_TRANSCRIPT,
        IngestionJobStatus.CHUNKING,
        IngestionJobStatus.EMBEDDING,
        IngestionJobStatus.INDEXING,
        IngestionJobStatus.READY,
    ]

    assert all(
        can_transition_job(current, target)
        for current, target in pairwise(states)
    )


@pytest.mark.parametrize(
    "terminal",
    [
        IngestionJobStatus.READY,
        IngestionJobStatus.PARTIAL_READY,
        IngestionJobStatus.FAILED,
    ],
)
def test_terminal_jobs_cannot_restart(terminal: IngestionJobStatus) -> None:
    assert not can_transition_job(
        terminal,
        IngestionJobStatus.EXTRACTING_METADATA,
    )


def test_active_job_can_fail_at_each_pipeline_stage() -> None:
    for state in (
        IngestionJobStatus.PENDING,
        IngestionJobStatus.EXTRACTING_METADATA,
        IngestionJobStatus.EXTRACTING_TRANSCRIPT,
        IngestionJobStatus.CHUNKING,
        IngestionJobStatus.EMBEDDING,
        IngestionJobStatus.INDEXING,
    ):
        assert can_transition_job(state, IngestionJobStatus.FAILED)

