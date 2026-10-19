from app.evaluations.rubric_checks import check_citation_presence
from app.schemas.evaluation import EvaluationArtifact, EvaluationEvidence


def test_citation_presence_check_requires_evidence() -> None:
    missing = EvaluationArtifact(answer_type="metric", answer_text="A factual answer.")
    cited = missing.model_copy(
        update={
            "evidence": [
                EvaluationEvidence(
                    citation_label="Content 1 · YouTube · metadata",
                    slot="content_1",
                    platform="youtube",
                    source_type="metadata",
                    text="views: 10",
                )
            ]
        }
    )

    assert check_citation_presence(missing).passed is False
    assert check_citation_presence(cited).passed is True
