"""Pre-call durable admission. Reserved ceilings are conservative estimates, not invoices."""
from app.core.config import setting_value
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime,UTC
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from app.core.access import current_principal,require_principal,owned_project
from app.core.config import get_settings
from app.core.request_limits import enforce_rate
from app.db.session import database_session
from app.db.models.account import AppUser,UserEntitlement,ProviderOperation,BudgetAccount,AnalysisReservation
from app.services.account_usage import latest_reservation,event
from app.llm.pricing_policy import load_pricing_registry,resolve_price
from app.core.active_pricing import active_registry

active_operation=ContextVar("active_provider_operation",default=None)


def paid_configuration(settings,kind):
    if getattr(settings,"provider_emergency_stop",True):
        raise HTTPException(403,"External provider execution is suspended.")
    allowance={"assistant":"assistant_admissions_per_analysis","semantic":"semantic_attempts_per_slot","diagnostic":"diagnostic_attempts_per_analysis"}.get(kind)
    if allowance and setting_value(settings,allowance) <= 0:
        raise HTTPException(403,"This provider operation has no approved attempt allowance.")
    ceiling=Decimal(settings.provider_operation_ceiling_usd)
    if ceiling<=0 or Decimal(settings.user_budget_usd)<=0 or Decimal(settings.global_budget_usd)<=0:
        raise HTTPException(403,"Approved nonzero spending bounds are required.")
    if kind=="extraction":
        from app.extraction.policy import configuration
        configuration(settings)
    else:
        from app.core.model_policy import model_configuration_error
        if model_configuration_error(settings) or not (getattr(settings,"gemini_api_key",None) or "").strip() or getattr(settings,"llm_cache_billing_mode","unknown") != "implicit":
            raise HTTPException(403,"Approved exact model, provider credentials and implicit cache billing configuration are required.")
        from app.core.active_pricing import active_registry
        configured = getattr(settings,"llm_active_pricing_json",None)
        registry = active_registry(configured,"llm") if configured is not None else load_pricing_registry()
        price=resolve_price(registry,settings.llm_provider,settings.llm_model,settings.llm_estimate_service_tier,datetime.now(UTC).date())
        if not price or not settings.provider_input_byte_limit:
            raise HTTPException(403,"Exact model/tier pricing and a bounded input budget are required.")
        # Every UTF-8 byte is conservatively budgeted as a token; SDK output cap includes thinking.
        maximum=(Decimal(settings.provider_input_byte_limit+setting_value(settings,'provider_schema_token_allowance'))*Decimal(price["input_per_million"])+Decimal(max(setting_value(settings,'llm_max_output_tokens'),setting_value(settings,'assistant_max_output_tokens'),setting_value(settings,'semantic_max_output_tokens'),setting_value(settings,'diagnostic_max_output_tokens')))*Decimal(price["output_per_million"]))/Decimal(1000000)
        if ceiling<maximum:
            raise HTTPException(403,"Operation ceiling is smaller than the configured token bound.")
    return ceiling


def admit(session,principal,project_id,kind,*,slot="",snapshot_id=None,settings=None,rate=True):
    settings=settings or get_settings()
    ceiling=paid_configuration(settings,kind)
    if kind=="extraction":
        raise HTTPException(403,"Use provider-specific per-slot extraction admission.")
    if rate: enforce_rate(settings,principal.user_id,"paid")
    owned_project(session,project_id,principal)
    user=session.get(AppUser,principal.user_id)
    if not user or user.status!="active": raise HTTPException(403,"Account unavailable.")
    # All admissions take global -> user locks in a fixed order.
    global_budget=session.scalar(select(BudgetAccount).where(BudgetAccount.id=="global").with_for_update())
    user_budget=session.scalar(select(BudgetAccount).where(BudgetAccount.id==principal.user_id).with_for_update())
    entitlement=session.scalar(select(UserEntitlement).where(UserEntitlement.user_id==principal.user_id).with_for_update())
    reservation=latest_reservation(session,project_id)
    if not reservation or reservation.user_id!=principal.user_id or reservation.state not in {"reserved","processing","completed"}:
        raise HTTPException(409,"A valid analysis admission is required.")
    if kind in {"assistant","diagnostic"} and reservation.state!="completed": raise HTTPException(409,"Complete this comparison before paid Assistant generation.")
    if kind in {"semantic","extraction"} and reservation.state=="completed": raise HTTPException(409,"Full re-analysis requires a new analysis credit.")
    if kind=="diagnostic":
        # The user budget lock serializes admissions across projects and API replicas.
        previous=session.scalar(select(ProviderOperation).where(ProviderOperation.user_id==principal.user_id,ProviderOperation.kind==kind).order_by(ProviderOperation.created_at.desc()).limit(1))
        if previous:
            if previous.state!="completed":
                raise HTTPException(409,"The previous diagnostic outcome requires reconciliation before another check.")
            created=previous.created_at
            if created.tzinfo is None:created=created.replace(tzinfo=UTC)
            remaining=setting_value(settings,'diagnostic_cooldown_seconds')-(datetime.now(UTC)-created).total_seconds()
            if remaining>0:
                from math import ceil
                raise HTTPException(429,"Wait before checking the LLM again.",headers={"Retry-After":str(ceil(remaining))})
    operations=session.scalars(select(ProviderOperation).where(ProviderOperation.reservation_id==reservation.id,ProviderOperation.kind==kind,ProviderOperation.slot==slot).order_by(ProviderOperation.attempt)).all()
    maximum={"assistant":setting_value(settings,'assistant_admissions_per_analysis'),"semantic":setting_value(settings,'semantic_attempts_per_slot'),"diagnostic":setting_value(settings,'diagnostic_attempts_per_analysis')}.get(kind,0)
    if len(operations)>=maximum: raise HTTPException(403,"Provider attempt allowance exhausted.")
    if kind=="semantic" and operations and operations[-1].state!="completed":
        raise HTTPException(409,"The prior provider outcome must be reconciled before a safe retry.")
    if not global_budget or not user_budget or global_budget.reserved_usd+ceiling>Decimal(settings.global_budget_usd) or user_budget.reserved_usd+ceiling>Decimal(settings.user_budget_usd):
        raise HTTPException(403,"Configured estimated spending allowance is exhausted.")
    global_budget.reserved_usd+=ceiling;user_budget.reserved_usd+=ceiling
    operation=ProviderOperation(id=str(uuid4()),reservation_id=reservation.id,project_id=project_id,user_id=principal.user_id,kind=kind,slot=slot,attempt=len(operations)+1,state="admitted",ceiling_usd=ceiling,snapshot_id=snapshot_id)
    if kind in {"assistant","semantic","diagnostic"}:
        registry = active_registry(settings.llm_active_pricing_json,"llm") if getattr(settings,"llm_active_pricing_json",None) is not None else load_pricing_registry()
        operation.provider_details={"pricing":resolve_price(registry,settings.llm_provider,settings.llm_model,settings.llm_estimate_service_tier,datetime.now(UTC).date()),"model":settings.llm_model}
    session.add(operation);session.flush()
    event(session,principal.user_id,"provider_admitted",operation.id,{"kind":kind,"ceiling_usd":str(ceiling)})
    return operation.id


def finish(operation_id,*,known_response):
    if operation_id is None:return
    with database_session() as session:
        operation=session.get(ProviderOperation,operation_id)
        if not operation or operation.state!="admitted":return
        operation.state="completed" if known_response else "needs_reconciliation"
        # Keep the entire ceiling charged against lifetime budget; never treat unknown billing as zero.
        event(session,operation.user_id,"provider_"+operation.state,operation.id)
        if not known_response:
            reservation=session.get(AnalysisReservation,operation.reservation_id)
            if reservation.state!="completed":reservation.state="needs_reconciliation"


def admit_current(project_id,kind,**kwargs):
    with database_session() as session:
        return admit(session,require_principal(),project_id,kind,**kwargs)


def check_input(messages):
    if not active_operation.get():raise HTTPException(403,"Provider invocation requires durable admission.")
    size=sum(len(str(getattr(message,"content",message)).encode("utf-8")) for message in messages)
    if size>get_settings().provider_input_byte_limit:raise HTTPException(413,"Provider input exceeds the approved token budget.")


@contextmanager
def operation_scope(operation_id):
    handle=active_operation.set(operation_id)
    try:yield
    finally:active_operation.reset(handle)
