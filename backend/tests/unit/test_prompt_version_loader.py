from app.llm.prompt_registry import get_prompt
from app.llm.structured_outputs import StructuredAnswerType


def test_each_structured_prompt_has_a_version() -> None:
    for answer_type in StructuredAnswerType:
        prompt = get_prompt(answer_type)
        assert prompt.name
        assert prompt.version
