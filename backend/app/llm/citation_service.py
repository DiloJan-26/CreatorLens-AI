from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.llm.structured_outputs import EvidenceItem
from app.models.chat import Citation


MISSING_EVIDENCE_WARNING = (
    "The available evidence does not support every factual claim; treat the "
    "answer as limited rather than confirmed."
)


class CitationValidationResult(BaseModel):
    evidence: list[EvidenceItem] = Field(default_factory=list)
    invalid_citation_labels: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_grounded(self) -> bool:
        return bool(self.evidence) and not self.invalid_citation_labels


def validate_evidence_items(
    evidence: Sequence[EvidenceItem],
    citations: Sequence[Citation],
    *,
    factual_claims_present: bool,
) -> CitationValidationResult:
    citation_by_label = {
        citation.citation_label: citation
        for citation in citations
        if citation.citation_label.strip()
    }
    grounded: list[EvidenceItem] = []
    invalid_labels: list[str] = []

    for item in evidence:
        citation = citation_by_label.get(item.citation_label)
        if citation is None:
            if item.citation_label not in invalid_labels:
                invalid_labels.append(item.citation_label)
            continue

        grounded.append(
            item.model_copy(
                update={
                    "slot": _citation_slot(citation.slot),
                    "platform": citation.platform,
                    "source_type": citation.source_type,
                    "excerpt": citation.text,
                }
            )
        )

    warnings: list[str] = []
    if invalid_labels:
        warnings.append(
            "One or more model-provided citation labels were not present in "
            "the retrieved evidence and were removed."
        )
    if factual_claims_present and not grounded:
        warnings.append(MISSING_EVIDENCE_WARNING)

    return CitationValidationResult(
        evidence=grounded,
        invalid_citation_labels=invalid_labels,
        warnings=warnings,
    )


def _citation_slot(value: str | None) -> str | None:
    if value in {"content_1", "content_2"}:
        return value
    return None

