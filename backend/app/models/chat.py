from typing import Literal

from pydantic import BaseModel


ChatRole = Literal["user", "assistant", "system"]
QuestionIntent = Literal[
    "metrics",
    "creator_info",
    "hook_comparison",
    "content_summary",
    "performance_reasoning",
    "improvement_suggestions",
    "general",
]


class LLMHealthResponse(BaseModel):
    status: str
    provider: str
    model: str
    configured: bool
    message: str | None = None


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    project_id: str
    role: ChatRole
    content: str
    created_at: str


class ChatSession(BaseModel):
    session_id: str
    project_id: str
    created_at: str
    updated_at: str


class ChatHistoryResponse(BaseModel):
    project_id: str
    session_id: str
    messages: list[ChatMessage]


class CreateChatSessionResponse(BaseModel):
    project_id: str
    session_id: str
    message: str


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatStreamRequest(BaseModel):
    message: str
    session_id: str | None = None


class Citation(BaseModel):
    platform: str
    source_type: str
    citation_label: str
    text: str
    score: float | None = None


class RagContext(BaseModel):
    project_id: str
    intent: QuestionIntent
    structured_context: str
    retrieved_context: str
    citations: list[Citation]


class ChatStreamEvent(BaseModel):
    event: str
    data: dict


class AssistantFinalResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation]
