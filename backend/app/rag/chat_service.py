import json
import logging
from collections.abc import AsyncIterator
from decimal import Decimal
from time import perf_counter
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import get_settings
from app.llm.prompt_registry import get_prompt
from app.llm.cost_estimation import estimate_cost_usd
from app.llm.token_usage import TokenUsage, parse_token_usage
from app.llm.tracing import build_trace_metadata, trace_span
from app.llm.structured_output_service import (
    parse_structured_output,
    render_structured_answer,
    structured_answer_json_schema,
)
from app.llm.structured_outputs import (
    ComparisonAnswer,
    EvidenceItem,
    MetricAnswer,
    RecommendationAnswer,
    StructuredAnswer,
    StructuredAnswerType,
)
from app.models.chat import ChatMessage, ChatStreamRequest, Citation
from app.rag.query_router import parse_target_reference_slots
from app.rag.context_builder import (
    RagContextProjectNotFoundError,
    RagContextValidationError,
    build_direct_answer_if_possible,
    build_rag_context,
)
from app.rag.retrieval_service import RetrievalProjectNotFoundError
from app.services.chat_memory_service import (
    ChatProjectNotFoundError,
    ChatSessionNotFoundError,
    ChatValidationError,
    add_message,
    create_or_get_session,
    get_recent_messages,
)
from app.services.llm_service import LLMConfigurationError, get_llm
from app.services.qdrant_service import QdrantConfigurationError
from app.services.llm_observability_service import (
    complete_llm_run,
    fail_llm_run,
    get_project_runtime_signals,
    record_cost_event,
    start_llm_run,
)
from app.services.storage_compat_service import save_chat_citations


logger = logging.getLogger(__name__)


def build_system_prompt() -> str:
    return "\n".join(
        [
            "You are CreatorLens AI, a senior short-form content strategist and RAG assistant.",
            "You combine general creator marketing reasoning with specialist evidence from the provided content sources.",
            "The compared items are always called Content 1 and Content 2. Never use Video A, Video B, or any other label.",
            "Always include the platform name: YouTube, Instagram, or Facebook.",
            "Use confirmed public metrics only. Say Unavailable when public data is missing.",
            "Do not invent views, likes, comments, reactions, shares, follower counts, subscriber counts, engagement rates, dates, duration, or transcript details.",
            "Distinguish confirmed metric performance from heuristic content-quality signals such as Hook Analysis and Creator Insight Score.",
            "Creator Insight Scores are heuristic review signals, not guaranteed performance predictions.",
            "Metadata Availability supports confidence only; it is not a performance score or creator quality score.",
            "If metric data is incomplete, say the comparison is limited.",
            "For strategy, performance, hook, improvement, and rewrite questions, always give enough reasoning for a creator or marketer to take action.",
            "Never give one-line or one-paragraph answers for strategy, improvement, hook, or rewrite questions.",
            "Use clear numbered sections with diagnosis, evidence, specific changes, and next steps.",
            "If the user asks for N improvement points, return exactly N numbered points — no more, no fewer.",
            "Each improvement point must include: the issue, the evidence from retrieved sources, the specific change to make, and why that change should help.",
            "For improvement questions, identify what the target content currently does, what the reference content does better, and provide concrete actionable points.",
            "For rewrite questions, provide diagnosis of what is weak, a rewritten opening, why it is stronger, and an optional alternative version.",
            "For hook questions, identify hook type for both contents, which opening is stronger and exactly why, a specific improvement, and an example rewritten hook.",
            "For performance reasoning, compare confirmed metrics first, then hook, caption, CTA, and audience angle differences.",
            "Complete every answer fully before the citations are shown. Do not stop mid-sentence or mid-section.",
            "Use citations only from backend-provided source labels. Do not fabricate citation labels.",
            "Use backend source labels in the structured evidence field only; do not reproduce labels inside display text.",
            "If evidence is limited, state exactly what is missing and what you are basing your answer on.",
            "Never claim Instagram underperformed solely from missing views.",
            "If Facebook cross-post data is not connected, say combined Meta performance may be incomplete.",
            "Treat the structured Content 1 and Content 2 metadata as the source of truth for confirmed public metrics.",
        ]
    )


def format_chat_history(messages: list[ChatMessage]) -> str:
    if not messages:
        return "No previous conversation."

    recent_messages = messages[-10:]

    return "\n".join(
        f"{message.role}: {_compact_text(message.content, max_length=260)}"
        for message in recent_messages
    )


async def stream_chat_answer(
    project_id: str,
    request: ChatStreamRequest,
) -> AsyncIterator[str]:
    assistant_answer = ""
    session_id = request.session_id
    citations: list[Citation] = []
    settings = get_settings()
    llm_run_id: str | None = None
    usage = TokenUsage()
    llm_latency_ms: int | None = None
    langsmith_trace_id: str | None = None
    root_trace_context: Any = None
    root_trace: Any = None
    trace_status = "error"

    try:
        question = request.message.strip()

        if not question:
            raise ChatValidationError("Message must not be empty.")

        session = create_or_get_session(
            project_id=project_id,
            session_id=session_id,
        )
        session_id = session.session_id
        root_trace_context = trace_span(
            "creatorlens.rag_response",
            inputs={"project_id": project_id, "question_length": len(question)},
            metadata=build_trace_metadata(
                project_id=project_id,
                session_id=session_id,
                llm_model=settings.llm_model,
            ),
        )
        root_trace = root_trace_context.__enter__()
        langsmith_trace_id = root_trace.trace_id

        add_message(
            project_id=project_id,
            session_id=session_id,
            role="user",
            content=question,
        )
        recent_messages = get_recent_messages(
            project_id=project_id,
            session_id=session_id,
            limit=10,
        )
        with trace_span(
            "creatorlens.retrieval",
            run_type="retriever",
            inputs={"project_id": project_id, "question_length": len(question)},
            metadata=build_trace_metadata(
                project_id=project_id,
                session_id=session_id,
            ),
        ) as retrieval_trace:
            rag_context = build_rag_context(
                project_id=project_id,
                message=question,
                recent_messages=recent_messages,
            )
            if langsmith_trace_id is None:
                langsmith_trace_id = retrieval_trace.trace_id
            retrieval_trace.set_outputs(
                {
                    "retrieval_run_id": rag_context.retrieval_run_id,
                    "retrieval_latency_ms": rag_context.retrieval_latency_ms,
                    "retrieved_chunk_count": rag_context.retrieved_chunk_count,
                    "source_balance": rag_context.source_balance,
                }
            )
        direct_answer = build_direct_answer_if_possible(
            project_id=project_id,
            message=question,
            rag_context=rag_context,
        )

        if direct_answer is not None:
            prompt_name = "deterministic_metric_answer"
            prompt_version = "1.0.0"
            runtime_signals = get_project_runtime_signals(project_id)
            usage = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
            llm_run_id = start_llm_run(
                project_id=project_id,
                session_id=session_id,
                retrieval_run_id=rag_context.retrieval_run_id,
                llm_provider="internal",
                llm_model="deterministic_metric_answer",
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                retrieved_chunk_count=rag_context.retrieved_chunk_count,
                source_balance=rag_context.source_balance,
            )
            assistant_answer = str(direct_answer["answer"]).strip()
            citations = [
                citation
                for citation in direct_answer["citations"]
                if isinstance(citation, Citation)
            ]
            structured_answer = _structured_direct_answer(
                answer=assistant_answer,
                intent=rag_context.intent,
                citations=citations,
            )
            yield sse_event(
                "trace",
                _trace_payload(
                    mode="direct_metric_answer",
                    model=settings.llm_model,
                    intent=rag_context.intent,
                    rag_context=rag_context,
                    recent_messages=recent_messages,
                    citations=citations,
                    structured_answer_type=structured_answer.answer_type,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    fallback_used=False,
                ),
            )
            yield _structured_answer_event(
                structured_answer,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                fallback_used=False,
                warnings=[],
            )

            for token in _direct_answer_tokens(assistant_answer):
                yield sse_event("token", {"text": token})

            assistant_message = add_message(
                project_id=project_id,
                session_id=session_id,
                role="assistant",
                content=assistant_answer,
            )
            with trace_span(
                "creatorlens.citations",
                inputs={"citation_count": len(citations)},
                metadata=build_trace_metadata(
                    project_id=project_id,
                    session_id=session_id,
                    intent=rag_context.intent,
                    retrieval_run_id=rag_context.retrieval_run_id,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                ),
            ) as citation_trace:
                save_chat_citations(
                    message_id=assistant_message.message_id,
                    project_id=project_id,
                    session_id=session_id,
                    citations=[citation.model_dump() for citation in citations],
                )
                citation_trace.set_outputs({"persisted": len(citations)})
            complete_llm_run(
                llm_run_id,
                usage=usage,
                retrieval_latency_ms=rag_context.retrieval_latency_ms,
                llm_latency_ms=0,
                retrieved_chunk_count=rag_context.retrieved_chunk_count,
                source_balance=rag_context.source_balance,
                cache_hit=runtime_signals.cache_hit,
                cache_miss=runtime_signals.cache_miss,
                transcript_provider=runtime_signals.transcript_provider,
                transcript_fallback_used=runtime_signals.transcript_fallback_used,
                embedding_reused=runtime_signals.embedding_reused,
                langsmith_trace_id=langsmith_trace_id,
            )
            record_cost_event(
                llm_run_id=llm_run_id,
                project_id=project_id,
                llm_provider="internal",
                llm_model="deterministic_metric_answer",
                usage=usage,
                estimated_cost_usd=Decimal("0"),
                pricing_source="deterministic-no-llm",
            )
            yield sse_event(
                "citations",
                {"citations": [citation.model_dump() for citation in citations]},
            )
            yield sse_event(
                "done",
                {
                    "session_id": session_id,
                    "status": "complete",
                },
            )
            trace_status = "complete"
            return

        citations = rag_context.citations
        history_text = format_chat_history(recent_messages)
        prompt_context_summary = _prompt_context_summary(
            rag_context=rag_context,
            history_message_count=len(recent_messages),
            citation_count=len(citations),
        )
        target_slot, reference_slot = parse_target_reference_slots(question)
        answer_type = _answer_type_for_intent(rag_context.intent)
        with trace_span(
            "creatorlens.prompt",
            run_type="prompt",
            inputs={"answer_type": answer_type.value},
            metadata=build_trace_metadata(
                project_id=project_id,
                session_id=session_id,
                intent=rag_context.intent,
                retrieval_run_id=rag_context.retrieval_run_id,
                llm_model=settings.llm_model,
                retrieved_chunk_count=rag_context.retrieved_chunk_count,
                source_balance=rag_context.source_balance,
            ),
        ) as prompt_trace:
            prompt = get_prompt(answer_type)
            prompt_trace.set_outputs(
                {"prompt_name": prompt.name, "prompt_version": prompt.version}
            )
        runtime_signals = get_project_runtime_signals(project_id)
        llm_run_id = start_llm_run(
            project_id=project_id,
            session_id=session_id,
            retrieval_run_id=rag_context.retrieval_run_id,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            retrieved_chunk_count=rag_context.retrieved_chunk_count,
            source_balance=rag_context.source_balance,
        )
        llm = get_llm(streaming=False)
        messages = [
            SystemMessage(
                content="\n\n".join(
                    [
                        build_system_prompt(),
                        prompt.system_prompt,
                        "Required JSON schema:\n"
                        + json.dumps(
                            structured_answer_json_schema(answer_type),
                            ensure_ascii=False,
                        ),
                    ]
                )
            ),
            HumanMessage(
                content=prompt.render_user(
                    question=question,
                    intent=rag_context.intent,
                    structured_context=rag_context.structured_context,
                    retrieved_context=(
                        rag_context.retrieved_context.strip()
                        or "No retrieved source chunks were needed for this question."
                    ),
                    history_text=history_text,
                    citation_catalog=_citation_catalog(citations),
                    style_instructions=_answer_style_instructions(
                        rag_context.intent,
                        target_slot,
                        reference_slot,
                    ),
                )
            ),
        ]
        _maybe_debug_prompt(
            messages=messages,
            prompt_context_summary=prompt_context_summary,
        )
        yield sse_event(
            "trace",
            _trace_payload(
                mode="gemini_structured_answer",
                model=settings.llm_model,
                intent=rag_context.intent,
                rag_context=rag_context,
                recent_messages=recent_messages,
                citations=citations,
                prompt_context_summary=prompt_context_summary,
                structured_answer_type=answer_type,
                prompt_name=prompt.name,
                prompt_version=prompt.version,
            ),
        )

        llm_started_at = perf_counter()
        with trace_span(
            "creatorlens.llm",
            run_type="llm",
            inputs={
                "message_count": len(messages),
                "prompt_name": prompt.name,
                "prompt_version": prompt.version,
            },
            metadata=build_trace_metadata(
                project_id=project_id,
                session_id=session_id,
                intent=rag_context.intent,
                retrieval_run_id=rag_context.retrieval_run_id,
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                llm_model=settings.llm_model,
                retrieved_chunk_count=rag_context.retrieved_chunk_count,
                source_balance=rag_context.source_balance,
            ),
        ) as llm_trace:
            try:
                response = await llm.ainvoke(messages)
            finally:
                llm_latency_ms = max(
                    0,
                    round((perf_counter() - llm_started_at) * 1000),
                )
            usage = parse_token_usage(response)
            if langsmith_trace_id is None and llm_trace.trace_id:
                langsmith_trace_id = llm_trace.trace_id
            llm_trace.set_outputs(
                {
                    "llm_latency_ms": llm_latency_ms,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
            )
        parsed = parse_structured_output(
            _chunk_text(response),
            answer_type,
            citations=citations,
        )
        structured_answer = parsed.answer
        assistant_answer = render_structured_answer(structured_answer)

        if parsed.used_fallback or parsed.warnings:
            logger.warning(
                "Structured chat output required recovery project_id=%s "
                "session_id=%s answer_type=%s fallback=%s warning_count=%d",
                project_id,
                session_id,
                answer_type.value,
                parsed.used_fallback,
                len(parsed.warnings),
            )

        yield _structured_answer_event(
            structured_answer,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            fallback_used=parsed.used_fallback,
            warnings=parsed.warnings,
        )

        for token in _direct_answer_tokens(assistant_answer):
            yield sse_event("token", {"text": token})

        assistant_message = add_message(
            project_id=project_id,
            session_id=session_id,
            role="assistant",
            content=assistant_answer.strip()
            or "I could not generate a grounded answer from the available context.",
        )
        with trace_span(
            "creatorlens.citations",
            inputs={"citation_count": len(citations)},
            metadata=build_trace_metadata(
                project_id=project_id,
                session_id=session_id,
                intent=rag_context.intent,
                retrieval_run_id=rag_context.retrieval_run_id,
                prompt_name=prompt.name,
                prompt_version=prompt.version,
                llm_model=settings.llm_model,
            ),
        ) as citation_trace:
            save_chat_citations(
                message_id=assistant_message.message_id,
                project_id=project_id,
                session_id=session_id,
                citations=[citation.model_dump() for citation in citations],
            )
            citation_trace.set_outputs({"persisted": len(citations)})

        estimated_cost = estimate_cost_usd(
            usage,
            input_cost_per_million_usd=settings.llm_input_cost_per_million_usd,
            output_cost_per_million_usd=settings.llm_output_cost_per_million_usd,
        )
        complete_llm_run(
            llm_run_id,
            usage=usage,
            retrieval_latency_ms=rag_context.retrieval_latency_ms,
            llm_latency_ms=llm_latency_ms,
            retrieved_chunk_count=rag_context.retrieved_chunk_count,
            source_balance=rag_context.source_balance,
            cache_hit=runtime_signals.cache_hit,
            cache_miss=runtime_signals.cache_miss,
            transcript_provider=runtime_signals.transcript_provider,
            transcript_fallback_used=runtime_signals.transcript_fallback_used,
            embedding_reused=runtime_signals.embedding_reused,
            langsmith_trace_id=langsmith_trace_id,
        )
        record_cost_event(
            llm_run_id=llm_run_id,
            project_id=project_id,
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            usage=usage,
            estimated_cost_usd=estimated_cost,
            pricing_source=(
                "configured-env-per-million" if estimated_cost is not None else None
            ),
        )

        yield sse_event(
            "citations",
            {"citations": [citation.model_dump() for citation in citations]},
        )
        yield sse_event(
            "done",
            {
                "session_id": session_id,
                "status": "complete",
            },
        )
        trace_status = "complete"
    except (
        ChatProjectNotFoundError,
        RagContextProjectNotFoundError,
        RetrievalProjectNotFoundError,
    ):
        fail_llm_run(
            llm_run_id,
            error_code="PROJECT_NOT_FOUND",
            usage=usage,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        yield sse_event("error", {"message": "Project not found."})
    except ChatSessionNotFoundError:
        fail_llm_run(
            llm_run_id,
            error_code="CHAT_SESSION_NOT_FOUND",
            usage=usage,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        yield sse_event("error", {"message": "Chat session not found."})
    except (
        ChatValidationError,
        RagContextValidationError,
    ) as exc:
        fail_llm_run(
            llm_run_id,
            error_code="CHAT_VALIDATION_FAILED",
            usage=usage,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        yield sse_event("error", {"message": str(exc)})
    except QdrantConfigurationError:
        fail_llm_run(
            llm_run_id,
            error_code="QDRANT_NOT_CONFIGURED",
            usage=usage,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        yield sse_event("error", {"message": "Qdrant is not configured."})
    except LLMConfigurationError as exc:
        fail_llm_run(
            llm_run_id,
            error_code="LLM_NOT_CONFIGURED",
            usage=usage,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        yield sse_event("error", {"message": str(exc)})
    except Exception:
        fail_llm_run(
            llm_run_id,
            error_code="CHAT_STREAM_FAILED",
            usage=usage,
            llm_latency_ms=llm_latency_ms,
            langsmith_trace_id=langsmith_trace_id,
        )
        logger.exception(
            "Chat stream failed project_id=%s session_id=%s",
            project_id,
            session_id,
        )
        yield sse_event("error", {"message": "Could not stream chat answer."})
    finally:
        if root_trace is not None:
            root_trace.set_outputs(
                {
                    "status": trace_status,
                    "llm_run_id": llm_run_id,
                    "citation_count": len(citations),
                }
            )
        if root_trace_context is not None:
            root_trace_context.__exit__(None, None, None)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _trace_payload(
    mode: str,
    model: str,
    intent: str,
    rag_context: Any,
    recent_messages: list[ChatMessage],
    citations: list[Citation],
    prompt_context_summary: dict[str, int] | None = None,
    structured_answer_type: StructuredAnswerType | str | None = None,
    prompt_name: str | None = None,
    prompt_version: str | None = None,
    fallback_used: bool | None = None,
) -> dict[str, Any]:
    context_summary = prompt_context_summary or _prompt_context_summary(
        rag_context=rag_context,
        history_message_count=len(recent_messages),
        citation_count=len(citations),
    )

    payload: dict[str, Any] = {
        "mode": mode,
        "model": model,
        "intent": intent,
        "retrieved_sources": len(citations),
        "has_creator_insights": _has_creator_insights(rag_context),
        "has_structured_metadata": bool(rag_context.structured_context.strip()),
        "has_memory": len(recent_messages) > 1,
        "prompt_context_summary": context_summary,
    }

    if structured_answer_type is not None:
        payload["structured_answer_type"] = str(structured_answer_type)
    if prompt_name is not None:
        payload["prompt_name"] = prompt_name
    if prompt_version is not None:
        payload["prompt_version"] = prompt_version
    if fallback_used is not None:
        payload["fallback_used"] = fallback_used

    return payload


def _structured_answer_event(
    answer: StructuredAnswer,
    *,
    prompt_name: str,
    prompt_version: str,
    fallback_used: bool,
    warnings: list[str],
) -> str:
    return sse_event(
        "structured_answer",
        {
            "answer": answer.model_dump(mode="json"),
            "prompt": {
                "name": prompt_name,
                "version": prompt_version,
            },
            "fallback_used": fallback_used,
            "warnings": warnings,
        },
    )


def _answer_type_for_intent(intent: str) -> StructuredAnswerType:
    if intent in {"metrics", "creator_info", "metadata_missing"}:
        return StructuredAnswerType.METRIC
    if intent in {
        "performance_reasoning",
        "hook_analysis",
        "content_summary",
        "insight_summary",
    }:
        return StructuredAnswerType.COMPARISON
    return StructuredAnswerType.RECOMMENDATION


def _structured_direct_answer(
    *,
    answer: str,
    intent: str,
    citations: list[Citation],
) -> StructuredAnswer:
    answer_type = _answer_type_for_intent(intent)
    evidence = [
        EvidenceItem(
            citation_label=citation.citation_label,
            claim="Supports the deterministic answer from extracted project data.",
            slot=(
                citation.slot
                if citation.slot in {"content_1", "content_2"}
                else None
            ),
            platform=citation.platform,
            source_type=citation.source_type,
            excerpt=citation.text,
        )
        for citation in citations
    ]
    limitations = _direct_answer_limitations(answer)

    if answer_type == StructuredAnswerType.METRIC:
        return MetricAnswer(
            summary=answer,
            evidence=evidence,
            limitations=limitations,
        )
    if answer_type == StructuredAnswerType.COMPARISON:
        return ComparisonAnswer(
            winner="insufficient_evidence",
            confidence=0.0,
            evidence=evidence,
            limitations=limitations
            or ["The deterministic answer does not provide a structured winner."],
        )
    return RecommendationAnswer(
        summary=answer,
        evidence=evidence,
        limitations=limitations,
    )


def _direct_answer_limitations(answer: str) -> list[str]:
    normalized = answer.lower()
    if any(word in normalized for word in ("unavailable", "incomplete", "missing")):
        return [
            "One or more public fields are unavailable; missing values were not estimated."
        ]
    return []


def _citation_catalog(citations: list[Citation]) -> str:
    return json.dumps(
        [
            {
                "citation_label": citation.citation_label,
                "slot": citation.slot,
                "platform": citation.platform,
                "source_type": citation.source_type,
            }
            for citation in citations
        ],
        ensure_ascii=False,
    )


def _prompt_context_summary(
    rag_context: Any,
    history_message_count: int,
    citation_count: int,
) -> dict[str, int]:
    structured_context = rag_context.structured_context or ""
    retrieved_context = rag_context.retrieved_context or ""
    insight_context = _insight_context(structured_context)

    return {
        "structured_context_chars": len(structured_context),
        "retrieved_context_chars": len(retrieved_context),
        "insight_context_chars": len(insight_context),
        "history_message_count": history_message_count,
        "citation_count": citation_count,
    }


def _has_creator_insights(rag_context: Any) -> bool:
    return bool(_insight_context(rag_context.structured_context or ""))


def _insight_context(structured_context: str) -> str:
    marker = "Creator Insight Summary:"
    marker_index = structured_context.find(marker)

    if marker_index < 0:
        return ""

    return structured_context[marker_index:].strip()


def _maybe_debug_prompt(
    messages: list[SystemMessage | HumanMessage],
    prompt_context_summary: dict[str, int],
) -> None:
    if not get_settings().debug_rag_prompt:
        return

    print(
        "Prompt Context Preview:",
        json.dumps(
            {
                "message_count": len(messages),
                **prompt_context_summary,
            }
        ),
    )


def _answer_style_instructions(
    intent: str,
    target_slot: str | None = None,
    reference_slot: str | None = None,
) -> str:
    target_label = (
        "Content 1" if target_slot == "content_1"
        else "Content 2" if target_slot == "content_2"
        else "the target content"
    )
    reference_label = (
        "Content 2" if reference_slot == "content_2"
        else "Content 1" if reference_slot == "content_1"
        else "the reference content"
    )

    if intent == "performance_reasoning":
        return (
            "- Use this format:\n"
            "1. Quick verdict (1–2 sentences)\n"
            "2. Confirmed public metrics comparison (cite exact numbers or say Unavailable)\n"
            "3. Hook and first-seconds analysis for both contents\n"
            "4. Caption/description/CTA analysis for both contents\n"
            "5. Audience and content angle difference\n"
            "6. Metadata limitations\n"
            "7. Actionable next step for the creator"
        )

    if intent == "hook_analysis":
        return (
            "- Use this format:\n"
            "1. Content 1 hook type, first-second clarity, and evidence (quote from retrieved chunks if available)\n"
            "2. Content 2 hook type, first-second clarity, and evidence\n"
            "3. Which opening is stronger and the exact reason why\n"
            "4. Specific thing to fix in the weaker hook\n"
            "5. Example rewritten hook for the weaker content"
        )

    if intent == "improvement_suggestions":
        return (
            f"- The user wants to improve {target_label} using insights from {reference_label}.\n"
            "- If the user asked for a specific number of improvement points, return exactly that many numbered points.\n"
            "- Use this format:\n"
            f"1. Quick verdict (one sentence comparing {target_label} and {reference_label})\n"
            f"2. What {target_label} currently does (hook type, caption style, CTA, content angle)\n"
            f"3. What {reference_label} does better or differently\n"
            "4. Improvement points (exactly the number the user requested — each must include):\n"
            "   - Issue: the specific weakness\n"
            "   - Evidence: quote or reference from retrieved source chunks\n"
            "   - Change: the specific thing to do differently\n"
            "   - Why: why this change should improve engagement or clarity\n"
            "5. Optional example rewrite of the hook or caption opening\n"
            "6. Evidence limitation note if key transcript/caption data was unavailable"
        )

    if intent == "rewrite_request":
        return (
            "- Use this format:\n"
            "1. Diagnosis (what is weak or generic about the current opening or caption)\n"
            "2. Rewritten opening or caption (make it specific, hook-driven, and strong)\n"
            "3. Why this rewrite is stronger (cite hook type, clarity improvement, CTA)\n"
            "4. Optional alternative version\n"
            "5. What source evidence or pattern inspired the rewrite"
        )

    if intent == "metadata_missing":
        return (
            "- Use this format: Available fields for each content; Missing fields for each content; "
            "why they are likely unavailable; confirmation that no missing values were estimated."
        )

    if intent == "insight_summary":
        return (
            "- Summarize in sections:\n"
            "1. Content 1 Creator Insight Score, Hook Analysis, and top strengths\n"
            "2. Content 2 Creator Insight Score, Hook Analysis, and top strengths\n"
            "3. Comparison: confirmed metric winner, hook winner, overall insight winner\n"
            "4. Top recommendations\n"
            "5. Metadata confidence note"
        )

    return (
        "- Use a clear structured answer when comparing Content 1 and Content 2.\n"
        "- Include: diagnosis, evidence from retrieved chunks, specific recommendations, and next steps."
    )


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])

        return "".join(parts)

    return ""


def _direct_answer_tokens(answer: str) -> list[str]:
    lines = answer.splitlines()
    tokens: list[str] = []

    for index, line in enumerate(lines):
        suffix = "\n" if index < len(lines) - 1 else ""
        tokens.append(f"{line}{suffix}")

    return tokens or [answer]


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(value.split())

    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 3].rstrip()}..."
