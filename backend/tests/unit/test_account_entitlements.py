from uuid import uuid4
from dataclasses import replace
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select,func
from app.core.identity import Principal
from app.core.access import provision, owned_project,current_principal
from app.db.models.account import UserEntitlement,UsageEvent,AppUser,ProviderOperation
from app.db.repositories.project_repository import ProjectRepository
from app.services.account_usage import reserve,settle,balance


def account(session):
    principal=Principal(str(uuid4()),str(uuid4()),1)
    provision(session,principal)
    return principal


def project(session,principal):
    token=current_principal.set(principal)
    try:
        identifier=str(uuid4())
        ProjectRepository(session).create(project_id=identifier,content_1_url="https://youtu.be/a",content_2_url="https://youtu.be/b",content_1_platform="youtube",content_2_platform="youtube",status="created")
        return identifier
    finally: current_principal.reset(token)


def test_single_grant_and_owner_scope(db_session):
    a=account(db_session); b=account(db_session)
    for _ in range(3): provision(db_session,a)
    assert balance(db_session,a.user_id)==dict(granted=5,completed=0,reserved=0,available=5)
    assert db_session.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.user_id==a.user_id))==1
    p=project(db_session,a)
    with pytest.raises(HTTPException) as error: owned_project(db_session,p,b)
    assert error.value.status_code==404
    token=current_principal.set(b)
    try:
        assert ProjectRepository(db_session).get(p) is None
        assert ProjectRepository(db_session).list()==[]
    finally: current_principal.reset(token)


def test_five_settlements_and_sixth_rejected(db_session):
    a=account(db_session); p=project(db_session,a)
    for i in range(5):
        value,created=reserve(db_session,a,p,"request-"+str(i)); assert created
        settle(db_session,value.id,"completed",completion_mode="metrics_only")
        settle(db_session,value.id,"completed",completion_mode="metrics_only")
    assert balance(db_session,a.user_id)["available"]==0
    with pytest.raises(HTTPException): reserve(db_session,a,p,"request-6")
    assert db_session.get(AppUser,a.user_id) is not None


def test_one_active_and_idempotency(db_session):
    a=account(db_session); p=project(db_session,a); other=project(db_session,a)
    value,_=reserve(db_session,a,p,"request-1")
    assert reserve(db_session,a,p,"request-1")[0].id==value.id
    for pid,key in [(other,"request-1"),(p,"request-2")]:
        with pytest.raises(HTTPException) as error: reserve(db_session,a,pid,key)
        assert error.value.status_code==409
    assert balance(db_session,a.user_id)["reserved"]==1


@pytest.mark.parametrize("target",["failed","cancelled","expired"])
def test_failure_requires_verified_reconciliation(db_session,target):
    a=account(db_session);p=project(db_session,a);r,_=reserve(db_session,a,p,"request-1")
    with pytest.raises(HTTPException): settle(db_session,r.id,target)
    settle(db_session,r.id,"needs_reconciliation")
    assert balance(db_session,a.user_id)["reserved"]==1
    settle(db_session,r.id,target,verified_no_active_work=True)
    assert balance(db_session,a.user_id)["available"]==5


def test_uncertain_provider_never_releases_credit(db_session):
    a=account(db_session);p=project(db_session,a);r,_=reserve(db_session,a,p,"request-1")
    db_session.add(ProviderOperation(id=str(uuid4()),reservation_id=r.id,project_id=p,user_id=a.user_id,kind="extraction",slot="",attempt=1,state="needs_reconciliation",ceiling_usd=Decimal(".1")))
    db_session.flush()
    with pytest.raises(HTTPException): settle(db_session,r.id,"failed",verified_no_active_work=True)
    assert balance(db_session,a.user_id)["reserved"]==1


def test_suspended_user_cannot_reprovision(db_session):
    a=account(db_session);db_session.get(AppUser,a.user_id).status="suspended";db_session.flush()
    with pytest.raises(HTTPException): provision(db_session,a)


def test_completed_project_deletion_never_refunds(db_session):
    from app.db.models.project import Project
    a=account(db_session);p=project(db_session,a)
    reservation,_=reserve(db_session,a,p,"request-1")
    settle(db_session,reservation.id,"completed",completion_mode="metrics_only")
    db_session.delete(db_session.get(Project,p));db_session.flush()
    assert balance(db_session,a.user_id)["completed"]==1
    assert reservation.project_id==p and reservation.state=="completed"


def test_nested_chat_membership_cannot_be_forged(db_session):
    from app.db.repositories.chat_repository import ChatRepository
    a=account(db_session);first=project(db_session,a);second=project(db_session,a)
    repository=ChatRepository(db_session);chat=repository.create_session(first)
    with pytest.raises(ValueError):repository.save_message(second,chat["session_id"],"assistant","not allowed")


def test_same_url_cache_does_not_cross_owners(db_session):
    from app.db.repositories.content_item_repository import ContentItemRepository
    from app.db.repositories._utils import utc_now
    from app.db.models.content_item import ContentItem
    a=account(db_session);b=account(db_session);p=project(db_session,a)
    item=ContentItem(id=str(uuid4()),project_id=p,slot="content_1",platform="youtube",url="public-url",normalized_url="public-url",content_hash="a",metadata_hash="b",transcript_hash="c",extraction_status="ready",transcript_available=True,transcript_segment_count=1,created_at=utc_now(),updated_at=utc_now())
    db_session.add(item);db_session.flush()
    handle=current_principal.set(b)
    try:assert ContentItemRepository(db_session).find_reusable_by_normalized_url("public-url") is None
    finally:current_principal.reset(handle)
    handle=current_principal.set(a)
    try:assert ContentItemRepository(db_session).find_reusable_by_normalized_url("public-url").id==item.id
    finally:current_principal.reset(handle)


def test_logout_revocation_denies_reprovision(db_session):
    from app.core.access import insert_once
    from app.db.models.account import RevokedSession
    from app.db.repositories._utils import utc_now
    a=account(db_session)
    insert_once(db_session,RevokedSession,dict(id=a.session_id,user_id=a.user_id,created_at=utc_now()),"id")
    with pytest.raises(HTTPException):provision(db_session,a)


def test_ledger_is_append_only(db_session):
    a=account(db_session)
    row=db_session.scalar(select(UsageEvent).where(UsageEvent.user_id==a.user_id))
    row.kind="forged_grant"
    with pytest.raises(ValueError):db_session.flush()


def test_explicit_metrics_only_completion_never_calls_semantic(db_session,monkeypatch):
    from app.db.models.project import Project
    from app.db.repositories.content_item_repository import ContentItemRepository
    from app.db.repositories.metadata_repository import MetadataRepository
    from app.models.video import VideoMetadata
    from app.services.account_usage import complete_owned_analysis
    from app.services import semantic_service
    a=account(db_session);p=project(db_session,a);r,_=reserve(db_session,a,p,"request-1")
    db_session.get(Project,p).status="partial_ready"
    repository=ContentItemRepository(db_session)
    for slot,views in [("content_1",34021),("content_2",1527222)]:
        item=repository.upsert(project_id=p,slot=slot,platform="youtube",url="https://youtu.be/"+slot,extraction_status="partial",transcript_available=False,transcript_segment_count=0)
        MetadataRepository(db_session).create_snapshot(content_item=item,metadata=VideoMetadata(platform="youtube",slot=slot,url="https://youtu.be/"+slot,views=views,extraction_status="partial"))
    monkeypatch.setattr(semantic_service,"get_semantic_analysis",lambda *args:(_ for _ in ()).throw(AssertionError("Metrics-only completion must not depend on semantics")))
    value=complete_owned_analysis(db_session,a,p,True)
    assert value.state=="completed" and value.completion_mode=="metrics_only"
    assert balance(db_session,a.user_id)["completed"]==1


def test_account_migration_postgresql_sql_has_quarantine_and_constraints():
    import importlib.util
    from pathlib import Path
    from io import StringIO
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    path=Path(__file__).parents[2]/"alembic/versions/20261114_0012_account_ownership.py"
    spec=importlib.util.spec_from_file_location("account_migration",path);revision=importlib.util.module_from_spec(spec);spec.loader.exec_module(revision)
    output=StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql",opts={"as_sql":True,"output_buffer":output})):
        revision.upgrade()
    sql=output.getvalue()
    assert "owner_user_id" in sql and "NOT VALID" in sql and "uq_active_analysis_per_user" in sql
    assert "UPDATE projects" not in sql and "usage_events_append_only" in sql
    assert revision.down_revision=="20261113_0011"
    with pytest.raises(RuntimeError):revision.downgrade()


def test_historical_ownerless_project_stays_quarantined(db_session):
    a=account(db_session)
    identifier=str(uuid4())
    ProjectRepository(db_session).create(project_id=identifier,content_1_url="one",content_2_url="two",content_1_platform="youtube",content_2_platform="youtube",status="ready")
    with pytest.raises(HTTPException) as error:owned_project(db_session,identifier,a)
    assert error.value.status_code==404
    handle=current_principal.set(a)
    try:assert ProjectRepository(db_session).list()==[]
    finally:current_principal.reset(handle)


def test_forged_session_creation_cannot_rebind_another_project(db_session):
    from app.db.repositories.chat_repository import ChatRepository
    a=account(db_session);first=project(db_session,a);second=project(db_session,a)
    repository=ChatRepository(db_session);created=repository.create_session(first,"known-session")
    assert repository.create_session(first,"known-session")==created
    with pytest.raises(HTTPException) as error:repository.create_session(second,"known-session")
    assert error.value.status_code==404
    assert repository.get_session(first,"known-session")==created


def test_partial_status_without_usable_evidence_cannot_consume_credit(db_session):
    from app.db.models.project import Project
    from app.db.repositories.content_item_repository import ContentItemRepository
    from app.db.repositories.metadata_repository import MetadataRepository
    from app.models.video import VideoMetadata
    from app.services.account_usage import complete_owned_analysis
    a=account(db_session);p=project(db_session,a);reserve(db_session,a,p,"request-1")
    db_session.get(Project,p).status="partial_ready"
    for slot in ("content_1","content_2"):
        item=ContentItemRepository(db_session).upsert(project_id=p,slot=slot,platform="youtube",url="https://youtu.be/"+slot,extraction_status="partial",transcript_available=False,transcript_segment_count=0)
        MetadataRepository(db_session).create_snapshot(content_item=item,metadata=VideoMetadata(platform="youtube",slot=slot,url="https://youtu.be/"+slot,extraction_status="partial"))
    with pytest.raises(HTTPException) as error:complete_owned_analysis(db_session,a,p,False)
    assert error.value.status_code==409
    assert balance(db_session,a.user_id)["completed"]==0 and balance(db_session,a.user_id)["reserved"]==1
