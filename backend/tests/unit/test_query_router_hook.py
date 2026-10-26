from app.rag.query_router import classify_question, get_retrieval_plan
from app.schemas.retrieval import RetrievalMode


def test_hook_question_uses_hook_focused_mode() -> None:
    message = "Compare the opening hooks in the first few seconds."
    intent = classify_question(message)
    plan = get_retrieval_plan(intent, message)

    assert intent == "hook_analysis"
    assert plan["mode"] == RetrievalMode.HOOK_FOCUSED
    assert plan["multi_source"] is True
