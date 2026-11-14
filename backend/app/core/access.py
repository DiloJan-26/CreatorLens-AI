"""Verified request scope and project membership, shared by SQL and workers."""
from contextvars import ContextVar
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.core.identity import Principal
from app.db.models.account import AppUser, UserEntitlement, UsageEvent, BudgetAccount, RevokedSession
from app.db.models.project import Project
from app.db.repositories._utils import utc_now
from uuid import uuid4

current_principal = ContextVar("current_principal", default=None)


def require_principal():
    principal = current_principal.get()
    if principal is None:
        raise HTTPException(401, "Sign in with Google to continue.")
    return principal


def insert_once(session, model, values, key):
    dialect = session.get_bind().dialect.name
    statement = (pg_insert if dialect == "postgresql" else sqlite_insert)(model).values(**values)
    session.execute(statement.on_conflict_do_nothing(index_elements=[key]))


def provision(session, principal):
    now = utc_now()
    insert_once(session, AppUser, dict(id=principal.user_id,email=principal.email,display_name=principal.display_name,avatar_url=principal.avatar_url,status="active",role="user",created_at=now,updated_at=now), "id")
    user = session.scalar(select(AppUser).where(AppUser.id==principal.user_id).with_for_update())
    if user.status != "active" or session.get(RevokedSession, principal.session_id):
        raise HTTPException(403, "This account or session is unavailable.")
    insert_once(session, UserEntitlement, dict(user_id=user.id,granted=5,consumed=0,reserved=0), "user_id")
    insert_once(session, BudgetAccount, dict(id=user.id,reserved_usd=0), "id")
    insert_once(session, BudgetAccount, dict(id="global",reserved_usd=0), "id")
    insert_once(session, UsageEvent, dict(id=str(uuid4()),user_id=user.id,event_key="grant:"+user.id,kind="lifetime_grant",reference_id=user.id,details={"credits":5},created_at=now), "event_key")
    # Profile attributes have no authorization semantics.
    user.email, user.display_name, user.avatar_url, user.updated_at = principal.email, principal.display_name, principal.avatar_url, now
    return user


def owned_project(session, project_id, principal=None):
    principal = principal or require_principal()
    project = session.scalar(select(Project).where(Project.id==project_id,Project.owner_user_id==principal.user_id))
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project


def require_admin(session, principal=None):
    principal = principal or require_principal()
    user = session.get(AppUser,principal.user_id)
    if user is None or user.status != "active" or user.role != "admin":
        raise HTTPException(403, "Administrator access is required.")


def authorize_resource(session, project_id, model, identifier, principal=None):
    owned_project(session,project_id,principal)
    value = session.get(model,identifier)
    if value is None or value.project_id != project_id:
        raise HTTPException(404,"Resource not found.")
    return value
