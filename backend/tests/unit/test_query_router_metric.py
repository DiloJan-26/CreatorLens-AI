from app.rag.query_router import classify_question, get_retrieval_plan
from app.schemas.retrieval import RetrievalMode


def test_metric_question_uses_structured_metadata_mode() -> None:
    message = "Which content has more confirmed views?"
    intent = classify_question(message)
    plan = get_retrieval_plan(intent, message)

    assert intent == "metrics"
    assert plan["mode"] == RetrievalMode.METRIC_DIRECT
    assert plan["retrieve"] is False
