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
