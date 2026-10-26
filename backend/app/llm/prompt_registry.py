from functools import lru_cache
from pathlib import Path
from string import Formatter

import yaml
from pydantic import BaseModel, Field

from app.llm.structured_outputs import StructuredAnswerType


PROMPT_DIRECTORY = Path(__file__).resolve().parent / "prompts"


class PromptRegistryError(RuntimeError):
    """Raised when a versioned prompt cannot be loaded or rendered."""


class PromptDefinition(BaseModel):
    name: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    answer_type: StructuredAnswerType
    system_prompt: str = Field(min_length=1)
    user_template: str = Field(min_length=1)

    @property
    def required_variables(self) -> set[str]:
        return {
            field_name
            for _, field_name, _, _ in Formatter().parse(self.user_template)
            if field_name
        }

    def render_user(self, **values: str) -> str:
        missing = sorted(self.required_variables.difference(values))
        if missing:
            raise PromptRegistryError(
                f"Prompt {self.name} is missing variables: {', '.join(missing)}."
            )
        return self.user_template.format(**values)


@lru_cache
def load_prompt_registry() -> dict[StructuredAnswerType, PromptDefinition]:
    prompts: dict[StructuredAnswerType, PromptDefinition] = {}

    if not PROMPT_DIRECTORY.is_dir():
        raise PromptRegistryError("Prompt directory is missing.")

    for path in sorted(PROMPT_DIRECTORY.glob("*.yaml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            prompt = PromptDefinition.model_validate(payload)
        except Exception as exc:
            raise PromptRegistryError(f"Could not load prompt file: {path.name}.") from exc

        if prompt.answer_type in prompts:
            raise PromptRegistryError(
                f"Duplicate prompt for answer type: {prompt.answer_type.value}."
            )
        prompts[prompt.answer_type] = prompt

    missing = set(StructuredAnswerType).difference(prompts)
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise PromptRegistryError(f"Missing prompts for answer types: {names}.")

    return prompts


def get_prompt(answer_type: StructuredAnswerType | str) -> PromptDefinition:
    try:
        normalized = StructuredAnswerType(answer_type)
    except ValueError as exc:
        raise PromptRegistryError(f"Unsupported answer type: {answer_type}.") from exc
    return load_prompt_registry()[normalized]

