"""Validated loaders and deterministic artifacts for evaluation fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.schemas.evaluation import (
    EvaluationArtifact,
    EvaluationCaseDefinition,
    EvaluationEvidence,
    EvaluationFixtureContent,
    EvaluationFixtureCollection,
    EvaluationProjectFixture,
    EvidenceSourceType,
)


EVALUATIONS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = EVALUATIONS_DIR / "datasets"
FIXTURES_PATH = EVALUATIONS_DIR / "fixtures" / "project_fixtures_v1.json"
_SAFE_DATASET_NAME = re.compile(r"^[a-z0-9][a-z0-9_]+$")


class EvaluationFixtureError(ValueError):
    """Raised when a dataset or fixture is missing or invalid."""


def load_dataset(dataset_name: str) -> list[EvaluationCaseDefinition]:
    if not _SAFE_DATASET_NAME.fullmatch(dataset_name):
        raise EvaluationFixtureError("Dataset name is invalid.")

    path = DATASETS_DIR / f"{dataset_name}.jsonl"
    if not path.is_file():
        raise EvaluationFixtureError(f"Evaluation dataset '{dataset_name}' was not found.")

    cases: list[EvaluationCaseDefinition] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(EvaluationCaseDefinition.model_validate_json(line))
        except Exception as exc:
            raise EvaluationFixtureError(
                f"Invalid case at {path.name}:{line_number}."
            ) from exc

    case_ids = [case.case_id for case in cases]
    if not cases:
        raise EvaluationFixtureError(f"Evaluation dataset '{dataset_name}' is empty.")
    if len(case_ids) != len(set(case_ids)):
        raise EvaluationFixtureError(f"Evaluation dataset '{dataset_name}' has duplicate case IDs.")

    fixtures = load_project_fixtures()
    missing = sorted({case.project_fixture for case in cases} - set(fixtures))
    if missing:
        raise EvaluationFixtureError(
            f"Dataset references missing project fixtures: {', '.join(missing)}."
        )
    return cases


def load_project_fixtures() -> dict[str, EvaluationProjectFixture]:
    try:
        payload = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
        collection = EvaluationFixtureCollection.model_validate(payload)
    except Exception as exc:
        raise EvaluationFixtureError("Project evaluation fixtures are invalid.") from exc
    return {fixture.fixture_id: fixture for fixture in collection.fixtures}


def list_datasets() -> list[str]:
    return sorted(path.stem for path in DATASETS_DIR.glob("*.jsonl"))


def build_fixture_artifact(
    case: EvaluationCaseDefinition,
    fixture: EvaluationProjectFixture,
) -> EvaluationArtifact:
    """Build a stable reference artifact without network or model calls.

    These artifacts verify the evaluation harness and safety rubrics. Deployed
    model quality is evaluated by submitting or persisting real response data,
    not by treating this reference output as a model prediction.
    """

    evidence: list[EvaluationEvidence] = []
    missing_notes: list[str] = []
    metric_lines: list[str] = []

    for content in fixture.contents:
        slot_label = "Content 1" if content.slot == "content_1" else "Content 2"
        metadata_text = _metadata_text(slot_label, content.metadata)
        evidence.append(
            _evidence(content, "metadata", metadata_text)
        )
        evidence.append(
            _evidence(
                content,
                "description",
                content.description or content.title,
            )
        )

        if content.transcript_available and content.transcript_segments:
            first = content.transcript_segments[0]
            evidence.append(_evidence(content, "hook", str(first.get("text", ""))))
            transcript = " ".join(
                str(segment.get("text", "")).strip()
                for segment in content.transcript_segments
                if str(segment.get("text", "")).strip()
            )
            evidence.append(_evidence(content, "transcript", transcript))
        else:
            missing_notes.append(f"{slot_label} transcript is unavailable.")

        missing_fields = [str(item) for item in content.metadata.get("missing_fields", [])]
        if missing_fields:
            missing_notes.append(
                f"{slot_label} confirmed {', '.join(missing_fields)} are unavailable."
            )
        views = content.metadata.get("views")
        metric_lines.append(
            f"{slot_label} confirmed views: {views:,}."
            if isinstance(views, (int, float))
            else f"{slot_label} confirmed views are unavailable."
        )

    if case.expected_answer_type == "metric":
        lead = "Confirmed metric evidence was compared directly."
    elif case.expected_answer_type == "comparison":
        lead = "Content 1 and Content 2 were compared using only confirmed evidence."
    else:
        lead = (
            "Recommendations for Content 2 use the confirmed differences between "
            "Content 1 and Content 2."
        )

    required = set(case.required_sources)
    selected_evidence = [item for item in evidence if item.source_type in required]
    if not selected_evidence:
        selected_evidence = [item for item in evidence if item.source_type == "metadata"]
    represented_slots = {item.slot for item in selected_evidence}
    for slot in ("content_1", "content_2"):
        if slot in represented_slots:
            continue
        fallback = next(
            item
            for item in evidence
            if item.slot == slot and item.source_type == "metadata"
        )
        selected_evidence.append(fallback)

    limitations = list(dict.fromkeys(missing_notes or ["No additional evidence limitations were found."]))
    answer_text = "\n".join([lead, *metric_lines, "Limitations: " + " ".join(limitations)])
    return EvaluationArtifact(
        answer_type=case.expected_answer_type,
        answer_text=answer_text,
        evidence=selected_evidence,
        limitations=limitations,
    )


def _evidence(
    content: EvaluationFixtureContent,
    source_type: EvidenceSourceType,
    text: str,
) -> EvaluationEvidence:
    slot_label = "Content 1" if content.slot == "content_1" else "Content 2"
    return EvaluationEvidence(
        citation_label=f"{slot_label} · {content.platform.title()} · {source_type}",
        slot=content.slot,
        platform=content.platform,
        source_type=source_type,
        text=text or "Unavailable",
    )


def _metadata_text(slot_label: str, metadata: dict) -> str:
    values = []
    for name, value in metadata.items():
        if name == "missing_fields":
            continue
        rendered = "Unavailable" if value is None else str(value)
        values.append(f"{name}: {rendered}")
    return f"{slot_label} confirmed metadata. " + "; ".join(values)
