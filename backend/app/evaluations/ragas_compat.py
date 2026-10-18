"""Compatibility boundary for importing the configured RAGAS release."""

from importlib import import_module, util
from types import ModuleType
from typing import Any
import sys


_REMOVED_VERTEX_MODULE = "langchain_community.chat_models.vertexai"


class _UnavailableChatVertexAI:
    """Placeholder for an optional provider that CreatorLens does not use."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "Vertex AI evaluation is not configured. CreatorLens uses the "
            "configured Gemini provider instead."
        )


def load_ragas() -> ModuleType:
    """Import RAGAS without downgrading the application's LangChain stack.

    RAGAS 0.4.3 imports a legacy optional Vertex chat module that was removed
    from langchain-community 0.4. CreatorLens does not use Vertex AI, so a
    provider placeholder is registered only when that legacy module is absent.
    Remove this boundary after RAGAS publishes its upstream import fix.
    """

    if not _module_exists(_REMOVED_VERTEX_MODULE):
        compatibility_module = ModuleType(_REMOVED_VERTEX_MODULE)
        compatibility_module.ChatVertexAI = _UnavailableChatVertexAI  # type: ignore[attr-defined]
        sys.modules.setdefault(_REMOVED_VERTEX_MODULE, compatibility_module)

    return import_module("ragas")


def _module_exists(module_name: str) -> bool:
    if module_name in sys.modules:
        return True
    try:
        return util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
