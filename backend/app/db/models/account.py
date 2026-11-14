"""Account ownership and durable usage; identity is a canonical Supabase UUID."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index, Numeric, JSON, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.db.repositories._utils import utc_now


class AppUser(Base):
    __tablename__ = "app_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(512))
    display_name: Mapped[str | None] = mapped_column(String(512))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class RevokedSession(Base):
    __tablename__ = "revoked_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class UserEntitlement(Base):
    __tablename__ = "user_entitlements"
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id"), primary_key=True)
    granted: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    __table_args__ = (CheckConstraint("granted = 5 AND consumed >= 0 AND reserved >= 0 AND consumed + reserved <= granted", name="credit_bounds"),)


ACTIVE_STATES = ("reserved", "processing", "needs_reconciliation")


class AnalysisReservation(Base):
    __tablename__ = "analysis_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id"), nullable=False, index=True)
    # Durable identity intentionally survives deletion; not a cascading project FK.
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="reserved", nullable=False)
    completion_mode: Mapped[str | None] = mapped_column(String(32))
    job_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),
        Index("uq_active_analysis_per_user", "user_id", unique=True,
              postgresql_where=text("state IN ('reserved','processing','needs_reconciliation')"),
              sqlite_where=text("state IN ('reserved','processing','needs_reconciliation')")),)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id"), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BudgetAccount(Base):
    __tablename__ = "budget_accounts"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(24,12), default=Decimal(0), nullable=False)
    __table_args__ = (CheckConstraint("reserved_usd >= 0", name="budget_nonnegative"),)


class ProviderOperation(Base):
    __tablename__ = "provider_operations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("analysis_reservations.id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("app_users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    slot: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="admitted", nullable=False)
    ceiling_usd: Mapped[Decimal] = mapped_column(Numeric(24,12), nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(64))
    operation_key: Mapped[str | None] = mapped_column(String(64))
    billing_pool: Mapped[str | None] = mapped_column(String(128), index=True)
    reserved_quantity: Mapped[int | None] = mapped_column(Integer)
    provider_details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    __table_args__ = (UniqueConstraint("reservation_id", "kind", "slot", "attempt"),
        Index("uq_provider_operations_operation_key","operation_key",unique=True),
        CheckConstraint("reserved_quantity IS NULL OR reserved_quantity >= 0",name="provider_quantity_nonnegative"),)


class DispatchOutbox(Base):
    __tablename__ = "dispatch_outbox"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reservation_id: Mapped[str] = mapped_column(ForeignKey("analysis_reservations.id"), nullable=False)
    task_name: Mapped[str] = mapped_column(String(64), nullable=False)
    argument: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
