import json
from types import SimpleNamespace

from app.models.chat import (
    ChatMessage,
    ChatSession,
    ChatStreamRequest,
    Citation,
    RagContext,
)
from app.rag import chat_service


class _StructuredComparisonLlm:
    async def ainvoke(self, _messages: list[object]) -> SimpleNamespace:
        return SimpleNamespace(
            content=json.dumps(
                {
                    "answer_type": "comparison",
                    "winner": "content_1",
                    "confidence": 0.78,
                    "key_reasons": [
                        "Content 1 communicates its opening claim more directly."
                    ],
                    "evidence": [
                        {
                            "citation_label": "Content 1 hook",
                            "claim": "Content 1 states its claim immediately.",
                        },
                        {
                            "citation_label": "Content 2 transcript",
                            "claim": "Content 2 delays its main point.",
                        },
                    ],
                    "limitations": [
                        "Content 2 confirmed view count is unavailable."
                    ],
                    "recommendations": [],
                }
            )
        )


def test_comparison_chat_emits_validated_structure_and_citations(monkeypatch) -> None:
    project_id = "project-1"
    session_id = "session-1"
    citations = [
        Citation(
            slot="content_1",
            platform="YouTube",
            source_type="hook",
            citation_label="Content 1 hook",
            text="The opening states the result immediately.",
            score=0.9,
        ),
        Citation(
            slot="content_2",
            platform="Instagram",
            source_type="transcript",
            citation_label="Content 2 transcript",
            text="The opening builds context before the main point.",
            score=0.8,
        ),
    ]
    saved_citations: list[dict] = []

    monkeypatch.setattr(
        chat_service,
        "create_or_get_session",
        lambda **_kwargs: ChatSession(
            session_id=session_id,
            project_id=project_id,
            created_at="2026-10-18T00:00:00Z",
            updated_at="2026-10-18T00:00:00Z",
        ),
    )

    message_count = {"value": 0}

    def _add_message(**kwargs) -> ChatMessage:
        message_count["value"] += 1
        return ChatMessage(
            message_id=f"message-{message_count['value']}",
            session_id=session_id,
            project_id=project_id,
            role=kwargs["role"],
            content=kwargs["content"],
            created_at="2026-10-18T00:00:00Z",
        )

    monkeypatch.setattr(chat_service, "add_message", _add_message)
    monkeypatch.setattr(chat_service, "get_recent_messages", lambda **_kwargs: [])
    monkeypatch.setattr(
        chat_service,
        "build_rag_context",
        lambda **_kwargs: RagContext(
            project_id=project_id,
            intent="performance_reasoning",
            structured_context=(
                "Content 1 views: 1000\nContent 2 views: Unavailable"
            ),
            retrieved_context="Hook and transcript evidence",
            citations=citations,
        ),
    )
    monkeypatch.setattr(
        chat_service,
        "build_direct_answer_if_possible",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        chat_service,
        "get_llm",
        lambda **_kwargs: _StructuredComparisonLlm(),
    )
    monkeypatch.setattr(
        chat_service,
        "save_chat_citations",
        lambda **kwargs: saved_citations.extend(kwargs["citations"]),
    )
    monkeypatch.setattr(
        chat_service,
        "get_project_runtime_signals",
        lambda _project_id: SimpleNamespace(
            cache_hit=None,
            cache_miss=None,
            transcript_provider=None,
            transcript_fallback_used=None,
            embedding_reused=None,
        ),
    )
    monkeypatch.setattr(chat_service, "start_llm_run", lambda **_kwargs: None)
    monkeypatch.setattr(chat_service, "complete_llm_run", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(chat_service, "record_cost_event", lambda **_kwargs: False)

    async def _collect_events() -> list[str]:
        return [
            event
            async for event in chat_service.stream_chat_answer(
                project_id,
                ChatStreamRequest(message="Which performed better?"),
            )
        ]

    import asyncio

    events = asyncio.run(_collect_events())
    parsed_events = [_parse_sse_event(event) for event in events]
    structured = next(
        data for event, data in parsed_events if event == "structured_answer"
    )

    assert structured["answer"]["answer_type"] == "comparison"
    assert structured["answer"]["winner"] == "content_1"
    assert structured["answer"]["limitations"] == [
        "Content 2 confirmed view count is unavailable."
    ]
    assert {
        item["citation_label"] for item in structured["answer"]["evidence"]
    } == {"Content 1 hook", "Content 2 transcript"}
    assert structured["fallback_used"] is False
    assert any(event == "citations" for event, _data in parsed_events)
    assert len(saved_citations) == 2
    assert "1000" not in "".join(
        data["text"]
        for event, data in parsed_events
        if event == "token"
    )


def _parse_sse_event(value: str) -> tuple[str, dict]:
    event = "message"
    data = ""
    for line in value.strip().splitlines():
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data += line.removeprefix("data:").strip()
    return event, json.loads(data)
