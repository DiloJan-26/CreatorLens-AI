import pytest

from app.llm.prompt_registry import PromptRegistryError, get_prompt


def test_registry_loads_versioned_comparison_prompt() -> None:
    prompt = get_prompt("comparison")

    assert prompt.version == "1.0.0"
    assert prompt.answer_type == "comparison"
    assert "question" in prompt.required_variables
    assert "citation_catalog" in prompt.required_variables


def test_prompt_render_rejects_missing_variables() -> None:
    prompt = get_prompt("metric")

    with pytest.raises(PromptRegistryError):
        prompt.render_user(question="Which content has more views?")


def test_all_registered_prompts_render_chat_context() -> None:
    values = {
        "question": "Which performed better?",
        "intent": "performance_reasoning",
        "history_text": "No previous conversation.",
        "structured_context": "Content 1 views: 1000",
        "retrieved_context": "Content 1 hook evidence",
        "citation_catalog": "[]",
        "style_instructions": "Report explicit limitations.",
    }

    for answer_type in ("metric", "comparison", "recommendation"):
        rendered = get_prompt(answer_type).render_user(**values)
        assert values["question"] in rendered
        assert values["structured_context"] in rendered
