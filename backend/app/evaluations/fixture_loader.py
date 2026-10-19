"""Validated loaders and deterministic artifacts for evaluation fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.schemas.evaluation import (
    EvaluationArtifact,
    EvaluationCaseDefinition,
    EvaluationEvidence,
    EvaluationFixtureCollection,
    EvaluationFixtureContent,
    EvaluationProjectFixture,
    EvidenceSourceType,
)

EVALUATIONS_DIR = Path(__file__).resolve().parent
DATASETS_DIR = EVALUATIONS_DIR / "datasets"
FIXTURES_PATH = EVALUATIONS_DIR / "fixtures" / "project_fixtures_v1.json"
DATASET_VERSION = "1.1.0"
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
    """Build a question-specific simulated system output from stable fixtures."""

    evidence, missing_notes = _build_all_evidence(fixture)
    required = set(case.required_sources)
    selected = [item for item in evidence if item.source_type in required]
    if not selected:
        selected = [item for item in evidence if item.source_type == "metadata"]
    represented_slots = {item.slot for item in selected}
    for slot in ("content_1", "content_2"):
        if slot not in represented_slots:
            selected.append(
                next(
                    item for item in evidence
                    if item.slot == slot and item.source_type == "metadata"
                )
            )

    limitations = list(dict.fromkeys(
        missing_notes or ["No additional evidence limitations were found."]
    ))
    if case.expected_answer_type == "metric":
        answer = _build_metric_answer(case, fixture)
    elif case.expected_answer_type == "comparison":
        answer = _build_comparison_answer(case, fixture)
    else:
        answer = _build_recommendation_answer(case, fixture)
    return EvaluationArtifact(
        answer_type=case.expected_answer_type,
        answer_text=f"{answer}\nLimitations: {' '.join(limitations)}",
        evidence=selected,
        limitations=limitations,
    )


def build_reference_contexts(
    case: EvaluationCaseDefinition,
    fixture: EvaluationProjectFixture,
) -> list[str]:
    """Select expected evidence separately from the simulated retrieval output."""

    evidence, _ = _build_all_evidence(fixture)
    contexts = [
        item.text for item in evidence
        if item.source_type in set(case.required_sources)
    ]
    return contexts or [item.text for item in evidence if item.source_type == "metadata"]


def _build_all_evidence(
    fixture: EvaluationProjectFixture,
) -> tuple[list[EvaluationEvidence], list[str]]:
    evidence: list[EvaluationEvidence] = []
    missing_notes: list[str] = []
    for content in fixture.contents:
        slot_label = _slot_label(content.slot)
        evidence.append(
            _evidence(content, "metadata", _metadata_text(slot_label, content.metadata))
        )
        evidence.append(
            _evidence(content, "description", content.description or content.title)
        )
        if content.transcript_available and content.transcript_segments:
            evidence.append(_evidence(
                content,
                "hook",
                str(content.transcript_segments[0].get("text", "")),
            ))
            transcript = " ".join(
                str(segment.get("text", "")).strip()
                for segment in content.transcript_segments
                if str(segment.get("text", "")).strip()
            )
            evidence.append(_evidence(content, "transcript", transcript))
        else:
            missing_notes.append(f"{slot_label} transcript is unavailable.")
        missing_fields = [
            str(item).replace("_", " ")
            for item in content.metadata.get("missing_fields", [])
        ]
        if missing_fields:
            missing_notes.append(
                f"{slot_label} confirmed {', '.join(missing_fields)} are unavailable."
            )
    return evidence, missing_notes


def _build_metric_answer(
    case: EvaluationCaseDefinition,
    fixture: EvaluationProjectFixture,
) -> str:
    question = case.question.casefold()
    if "engagement" in question:
        metric_names, label = ("engagement_rate",), "engagement rate"
    elif "comment" in question:
        metric_names, label = ("comments",), "comments"
    elif "like" in question:
        metric_names, label = ("likes",), "likes"
    elif "follower" in question or "subscriber" in question:
        metric_names = ("follower_count", "subscriber_count")
        label = "follower or subscriber count"
    else:
        metric_names, label = ("views",), "views"

    lines = [f"Confirmed {label} comparison:"]
    numeric_values: list[tuple[str, float]] = []
    for content in fixture.contents:
        value = next((
            content.metadata.get(name)
            for name in metric_names
            if content.metadata.get(name) is not None
        ), None)
        slot_label = _slot_label(content.slot)
        if isinstance(value, (int, float)):
            numeric_values.append((slot_label, float(value)))
            rendered = f"{value:,.3f}".rstrip("0").rstrip(".")
            lines.append(f"{slot_label} confirmed {label}: {rendered}.")
        else:
            lines.append(f"{slot_label} confirmed {label}: Unavailable.")
    if len(numeric_values) == 2:
        winner = max(numeric_values, key=lambda item: item[1])[0]
        lines.append(f"{winner} has the higher confirmed {label}.")
    return "\n".join(lines)


def _build_comparison_answer(
    case: EvaluationCaseDefinition,
    fixture: EvaluationProjectFixture,
) -> str:
    question = case.question.casefold()
    if any(term in question for term in ("hook", "opening", "spoken")):
        lines = ["Opening hook comparison:"]
        for content in fixture.contents:
            hook = _segment_text(content, first=True)
            lines.append(
                f'{_slot_label(content.slot)} hook: "{hook}".'
                if hook else
                f"{_slot_label(content.slot)} hook is unavailable because its transcript is unavailable."
            )
        return "\n".join(lines)
    if any(term in question for term in ("act", "cta", "call to action")):
        lines = ["Call to action comparison:"]
        for content in fixture.contents:
            action = _segment_text(content, first=False) or content.description or content.title
            lines.append(f'{_slot_label(content.slot)} call to action evidence: "{action}".')
        return "\n".join(lines)
    if "message" in question:
        return "\n".join([
            "Content message comparison:",
            *[
                f"{_slot_label(content.slot)} message: {content.description or content.title}."
                for content in fixture.contents
            ],
        ])
    metric_case = case.model_copy(update={"question": "confirmed views"})
    return (
        "Performance comparison using Content 1 and Content 2:\n"
        f"{_build_metric_answer(metric_case, fixture)}"
    )


def _build_recommendation_answer(
    case: EvaluationCaseDefinition,
    fixture: EvaluationProjectFixture,
) -> str:
    question = case.question.casefold()
    contents_by_slot = {content.slot: content for content in fixture.contents}
    content_1 = contents_by_slot["content_1"]
    content_2 = contents_by_slot["content_2"]
    hook_1 = _segment_text(content_1, first=True)
    hook_2 = _segment_text(content_2, first=True)
    if "hook" in question:
        return (
            f'Content 1 hook evidence is "{hook_1}". Content 2 hook evidence is "{hook_2}". '
            "Recommend that Content 2 test a more concrete problem-led hook based on Content 1."
        )
    if any(term in question for term in ("call to action", "cta")):
        action_1 = _segment_text(content_1, first=False)
        return (
            f'Content 1 call to action evidence is "{action_1}". '
            "Recommend that Content 2 add one clear call to action asking viewers to save or follow."
        )
    if not content_2.transcript_available:
        if "description" in case.required_sources and "metadata" not in case.required_sources:
            description_2 = content_2.description or content_2.title
            return (
                f'Content 2 evidence: "{description_2}". '
                f"Recommend that Content 2 clarify the {description_2.lower()}."
            )
        return (
            "Content 2 transcript is unavailable. Recommend improving Content 2 using its confirmed "
            "metadata and description, while avoiding claims about its spoken hook."
        )
    return (
        f'Content 1 hook evidence is "{hook_1}" and Content 2 hook evidence is "{hook_2}". '
        "Recommend that Content 2 test Content 1's concrete problem framing while preserving its own message."
    )


def _segment_text(content: EvaluationFixtureContent, *, first: bool) -> str | None:
    if not content.transcript_available or not content.transcript_segments:
        return None
    value = str(content.transcript_segments[0 if first else -1].get("text", "")).strip()
    return value or None


def _slot_label(slot: str) -> str:
    return "Content 1" if slot == "content_1" else "Content 2"


def _evidence(
    content: EvaluationFixtureContent,
    source_type: EvidenceSourceType,
    text: str,
) -> EvaluationEvidence:
    slot_label = _slot_label(content.slot)
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
        values.append(f"{name.replace('_', ' ')}: {rendered}")
    return f"{slot_label} confirmed metadata. " + "; ".join(values)
