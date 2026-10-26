from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from functools import lru_cache
import logging
from types import TracebackType
from typing import Any

from app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


def build_trace_metadata(
    *,
    project_id: str,
    session_id: str | None = None,
    intent: str | None = None,
    retrieval_run_id: str | None = None,
    prompt_name: str | None = None,
    prompt_version: str | None = None,
    llm_model: str | None = None,
    retrieved_chunk_count: int | None = None,
    source_balance: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build bounded trace metadata without prompts, evidence, or secrets."""

    metadata: dict[str, Any] = {"project_id": project_id}
    optional = {
        "session_id": session_id,
        "intent": intent,
        "retrieval_run_id": retrieval_run_id,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "llm_model": llm_model,
        "retrieved_chunk_count": retrieved_chunk_count,
        "source_balance": source_balance,
    }
    metadata.update({key: value for key, value in optional.items() if value is not None})
    return metadata


@dataclass(slots=True)
class TraceSpan:
    run: Any = None

    @property
    def trace_id(self) -> str | None:
        value = getattr(self.run, "trace_id", None) or getattr(self.run, "id", None)
        return str(value) if value else None

    def set_outputs(self, outputs: dict[str, Any]) -> None:
        if self.run is None:
            return
        try:
            self.run.end(outputs=outputs)
        except Exception:
            logger.warning("LangSmith trace output update failed.", exc_info=True)


class OptionalTrace(AbstractContextManager[TraceSpan]):
    """A LangSmith span that becomes a no-op when tracing is unavailable."""

    def __init__(
        self,
        name: str,
        *,
        run_type: str,
        inputs: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
        settings: Settings | None = None,
    ) -> None:
        self.name = name
        self.run_type = run_type
        self.inputs = inputs or {}
        self.metadata = metadata or {}
        self.settings = settings or get_settings()
        self._context: Any = None
        self._span = TraceSpan()

    def __enter__(self) -> TraceSpan:
        if not self.settings.langsmith_tracing_configured:
            return self._span
        try:
            from langsmith.run_helpers import trace

            client = _langsmith_client(
                self.settings.langsmith_endpoint or None,
                self.settings.langsmith_api_key or "",
                self.settings.langsmith_workspace_id or None,
            )
            self._context = trace(
                self.name,
                run_type=self.run_type,
                inputs=self.inputs,
                metadata=self.metadata,
                project_name=self.settings.langsmith_project,
                client=client,
            )
            self._span = TraceSpan(self._context.__enter__())
        except Exception:
            self._context = None
            self._span = TraceSpan()
            logger.warning(
                "LangSmith trace start failed trace_name=%s",
                self.name,
                exc_info=True,
            )
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if self._context is None:
            return False
        try:
            self._context.__exit__(exc_type, exc_value, traceback)
        except Exception:
            logger.warning(
                "LangSmith trace finish failed trace_name=%s",
                self.name,
                exc_info=True,
            )
        return False


def trace_span(
    name: str,
    *,
    run_type: str = "chain",
    inputs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> OptionalTrace:
    return OptionalTrace(
        name,
        run_type=run_type,
        inputs=inputs,
        metadata=metadata,
    )


@lru_cache(maxsize=4)
def _langsmith_client(
    api_url: str | None,
    api_key: str,
    workspace_id: str | None,
) -> Any:
    from langsmith import Client

    return Client(
        api_url=api_url,
        api_key=api_key,
        workspace_id=workspace_id,
    )
