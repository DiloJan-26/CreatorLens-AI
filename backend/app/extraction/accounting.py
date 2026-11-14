"""One durable ledger for provider credit exposure and existing USD budgets.

The global budget row serializes credit-pool and per-slot admissions on PostgreSQL.
Neither a failed HTTP call nor a timeout releases estimated exposure automatically.
"""
from datetime import datetime, UTC
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4
from sqlalchemy import select, func
from fastapi import HTTPException
from app.core.access import owned_project, require_principal
from app.core.config import get_settings
from app.core.request_limits import enforce_rate
from app.db.session import database_session
from app.db.models.account import AppUser, UserEntitlement, BudgetAccount, ProviderOperation, AnalysisReservation, DispatchOutbox
from app.services.account_usage import latest_reservation, event
from app.extraction.policy import configuration, input_url, source_key, SLOTS, POLICY_VERSION, ExtractionSafetyError


def admit(session, principal, project_id, slot, url, platform, operation, *, settings=None, rate=True):
    settings = settings or get_settings()
    prices = configuration(settings)
    if slot not in SLOTS or operation not in {"metadata", "native_transcript"}:
        raise HTTPException(403, "Unsupported bounded extraction operation.")
    normalized = input_url(url, platform, settings)
    if rate:
        enforce_rate(settings, principal.user_id, "paid")
    project = owned_project(session, project_id, principal)
    expected = getattr(project, slot + "_url")
    if input_url(expected, getattr(project, slot + "_platform"), settings) != normalized:
        raise HTTPException(409, "Extraction source does not match the admitted content slot.")
    budgets = [session.scalar(select(BudgetAccount).where(BudgetAccount.id == key).with_for_update()) for key in ("global", principal.user_id)]
    entitlement = session.scalar(select(UserEntitlement).where(UserEntitlement.user_id == principal.user_id).with_for_update())
    user = session.get(AppUser, principal.user_id, populate_existing=True)
    reservation = latest_reservation(session, project_id)
    if not user or user.status != "active" or not entitlement or not reservation or reservation.user_id != principal.user_id or reservation.state not in {"reserved", "processing"}:
        raise HTTPException(409, "Active owned analysis admission required.")
    # A task must have claimed this exact durable outbox; an API call cannot borrow its reservation.
    outbox = session.get(DispatchOutbox, reservation.job_id) if reservation.job_id else None
    if not outbox or outbox.state != "claimed" or outbox.reservation_id != reservation.id:
        raise HTTPException(409, "Only authoritative claimed ingestion work can invoke extraction.")
    kind = "extraction_metadata" if operation == "metadata" else "extraction"
    previous = session.scalars(select(ProviderOperation).where(ProviderOperation.reservation_id == reservation.id, ProviderOperation.kind == kind, ProviderOperation.slot == slot).order_by(ProviderOperation.attempt)).all()
    maximum = 1 if operation == "metadata" else 2
    if len(previous) >= maximum or previous and previous[-1].state != "safe_failure":
        raise HTTPException(409, "Slot attempt bound reached or prior outcome is not safely retryable.")
    if operation == "native_transcript":
        preflight = session.scalar(select(ProviderOperation).where(ProviderOperation.reservation_id == reservation.id, ProviderOperation.kind == "extraction_metadata", ProviderOperation.slot == slot, ProviderOperation.state == "completed"))
        if not preflight or (preflight.provider_details or {}).get("source_key") != source_key(principal.user_id, normalized):
            raise HTTPException(409, "Completed metadata duration preflight required before transcription.")
        from app.extraction.policy import checked_duration
        checked_duration((preflight.provider_details or {}).get("verified_duration_seconds"), settings)
    in_flight = session.scalar(select(func.count()).select_from(ProviderOperation).where(ProviderOperation.kind.in_(["extraction", "extraction_metadata"]), ProviderOperation.state.in_(["admitted", "running", "needs_reconciliation"])))
    if in_flight >= settings.extraction_max_concurrent_operations:
        raise HTTPException(409, "Approved extraction concurrency bound reached.")
    key = source_key(principal.user_id, normalized)
    # Recreating a project cannot erase unknown/failed billing or buy free retries.
    historical = session.scalars(select(ProviderOperation).where(ProviderOperation.user_id == principal.user_id, ProviderOperation.reservation_id != reservation.id, ProviderOperation.provider_details["source_key"].as_string() == key)).all()
    if any(op.state != "safe_failure" and session.get(AnalysisReservation, op.reservation_id).state != "completed" for op in historical):
        raise HTTPException(409, "Previous extraction of this source requires reconciliation; project recreation cannot reset it.")
    pool = "supadata:" + settings.supadata_credit_pool
    # Same account pool is global across users, projects and retries, with no automatic reset.
    used = session.scalar(select(func.coalesce(func.sum(ProviderOperation.reserved_quantity), 0)).where(ProviderOperation.billing_pool == pool))
    if used + 1 > settings.supadata_credit_limit:
        raise HTTPException(403, "Approved prepaid provider-credit pool exhausted.")
    price = next(p for p in prices if p["operation"] == operation)
    ceiling = Decimal(settings.provider_operation_ceiling_usd)
    if any(b is None for b in budgets) or budgets[0].reserved_usd + ceiling > Decimal(settings.global_budget_usd) or budgets[1].reserved_usd + ceiling > Decimal(settings.user_budget_usd):
        raise HTTPException(403, "Estimated USD spending allowance exhausted.")
    for budget in budgets:
        budget.reserved_usd += ceiling
    attempt = len(previous) + 1
    operation_key = sha256(f"{reservation.id}:{slot}:{kind}:{attempt}:{key}".encode()).hexdigest()
    details = dict(price, policy_version=POLICY_VERSION, source_key=key, platform=platform,
                   estimated_cost_usd=price["allocated_unit_usd"], actual_billed_cost_usd=None,
                   reported_usage=None, estimated_quantity=1, cost_status="bounded_prepaid_estimate",
                   settlement="reserved", auto_recharge_disabled=True, provider_request_id=None)
    row = ProviderOperation(id=str(uuid4()), reservation_id=reservation.id, project_id=project_id,
                            user_id=principal.user_id, kind=kind, slot=slot, attempt=attempt,
                            state="admitted", ceiling_usd=ceiling, operation_key=operation_key,
                            billing_pool=pool, reserved_quantity=1, provider_details=details)
    session.add(row)
    session.flush()
    event(session, principal.user_id, "extraction_admitted", row.id, {"provider": "supadata", "operation": operation, "slot": slot, "attempt": attempt, "reserved_usd": str(ceiling), "reserved_credits": 1})
    return row.id


def claim(session, operation_id, principal):
    row = session.scalar(select(ProviderOperation).where(ProviderOperation.id == operation_id).with_for_update())
    if not row or row.user_id != principal.user_id:
        raise ExtractionSafetyError("Provider operation is not owned by this worker.")
    owned_project(session, row.project_id, principal)
    user = session.get(AppUser, row.user_id, populate_existing=True)
    reservation = session.get(AnalysisReservation, row.reservation_id, populate_existing=True)
    if not user or user.status != "active" or reservation.state not in {"reserved", "processing"} or row.state != "admitted":
        raise ExtractionSafetyError("Provider work is revoked, duplicate or requires reconciliation.")
    row.state = "running"
    event(session, row.user_id, "extraction_started", row.id)
    return dict(row.provider_details)


def finish(session, operation_id, state, *, response_status=None, request_id=None, verified_duration=None, latency_ms=None):
    if state not in {"completed", "unavailable", "safe_failure", "needs_reconciliation"}:
        raise ValueError("Invalid provider settlement.")
    row = session.scalar(select(ProviderOperation).where(ProviderOperation.id == operation_id).with_for_update())
    # Late responses cannot revive uncertain work or double-settle a terminal operation.
    if not row or row.state not in {"admitted", "running"}:
        return False
    row.state = state
    details = dict(row.provider_details or {})
    details.update(settlement=state, response_status=response_status,
                   finished_at=datetime.now(UTC).isoformat(), provider_request_id=request_id, latency_ms=latency_ms)
    if verified_duration is not None and details.get("operation") == "metadata":
        details["verified_duration_seconds"] = verified_duration
    if state == "safe_failure":
        details.update(cost_status="known_no_request_sent",estimated_cost_usd="0",estimated_quantity=0,known_billable_quantity=0)
    if state == "needs_reconciliation":
        details.update(cost_status="unknown_outcome_reserved", estimated_cost_usd=None)
        reservation = session.get(AnalysisReservation, row.reservation_id)
        if reservation.state in {"reserved", "processing"}:
            reservation.state = "needs_reconciliation"
    row.provider_details = details
    # Full credit and USD reservations remain counted even after known failures.
    event(session, row.user_id, "extraction_" + state, row.id,
          {"provider": "supadata", "operation": details.get("operation"), "response_status": response_status})
    return True


def begin_current(project_id, slot, url, platform, operation):
    principal = require_principal()
    with database_session() as session:
        identifier = admit(session, principal, project_id, slot, url, platform, operation)
    with database_session() as session:
        claim(session, identifier, principal)
    return identifier


def finish_current(identifier, state, **kwargs):
    with database_session() as session:
        return finish(session, identifier, state, **kwargs)


def public_operation(row):
    details = row.provider_details or {}
    # Explicit allowlist: never return URLs, raw requests, headers or provider bodies.
    return {"id": row.id, "reservation_id": row.reservation_id, "slot": row.slot,
            "attempt": row.attempt, "state": row.state, "reserved_usd": str(row.ceiling_usd),
            "reserved_credits": row.reserved_quantity,
            **{key: details.get(key) for key in ("provider", "operation", "tier", "pricing_policy", "policy_version", "billing_unit", "reported_usage", "estimated_quantity", "known_billable_quantity", "estimated_cost_usd", "actual_billed_cost_usd", "estimate_basis", "cost_status", "settlement", "latency_ms")}}
