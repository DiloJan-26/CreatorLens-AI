"""Validate matching parent/project identity on all new ORM writes."""
from sqlalchemy import event
from sqlalchemy.orm import Session


def _parent(session,model,identifier):
    value=next((x for x in session.new if isinstance(x,model) and x.id==identifier),None)
    return value if value is not None else session.get(model,identifier)


@event.listens_for(Session,"before_flush")
def validate_membership(session,flush_context,instances):
    from app.db.models.account import UsageEvent
    if any(isinstance(row,UsageEvent) for row in session.deleted) or any(isinstance(row,UsageEvent) and session.is_modified(row) for row in session.dirty):
        raise ValueError("Usage ledger events are append-only.")
    from app.db.models.chat import ChatSession,ChatMessage,ChatCitation
    from app.db.models.content_item import ContentItem
    from app.db.models.llm_observability import LlmRun,CostEvent
    from app.db.models.semantic_snapshot import SemanticSnapshot
    for value in list(session.new)+list(session.dirty):
        project_id=getattr(value,"project_id",None)
        if project_id is None:continue
        checks=[]
        if isinstance(value,SemanticSnapshot):
            if session.get_bind().dialect.name == "sqlite":
                from sqlalchemy import inspect
                if not inspect(session.connection()).has_table("content_items"):
                    from app.core.config import get_settings
                    if get_settings().application_access_mode == "authenticated":
                        raise ValueError("Authenticated snapshots require the full application database.")
                    continue  # Preserve the explicitly unauthenticated V1 SQLite semantic sidecar.
            checks.append((ContentItem,value.content_id))
        content_id=getattr(value,"content_item_id",None)
        if content_id:checks.append((ContentItem,content_id))
        if isinstance(value,(ChatMessage,ChatCitation)):checks.append((ChatSession,value.session_id))
        if isinstance(value,ChatCitation):checks.append((ChatMessage,value.message_id))
        if isinstance(value,CostEvent) and value.llm_run_id:checks.append((LlmRun,value.llm_run_id))
        for model,identifier in checks:
            parent=_parent(session,model,identifier)
            if parent is None or parent.project_id!=project_id:
                raise ValueError("Resource parent/project membership mismatch.")
            if isinstance(value,ChatCitation) and isinstance(parent,ChatMessage) and parent.session_id!=value.session_id:
                raise ValueError("Citation session membership mismatch.")
            if isinstance(value,SemanticSnapshot) and parent.slot!=value.slot:
                raise ValueError("Semantic slot membership mismatch.")
