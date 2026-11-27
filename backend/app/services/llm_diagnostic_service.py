"""Manual Engineering diagnostic; no free-form prompts, retries or background checks."""
from datetime import datetime, UTC
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.core.access import require_principal
from app.core.config import get_settings, setting_value
from app.core.engineering_access import require_engineering
from app.services import provider_admission as admission
from app.services.llm_service import get_llm, _tracked_diagnostic_invoke, _message_text, LLMConfigurationError

PROMPT = "Reply with OK."


def provider_failure(error):
    """Classify structured status codes, never disclose raw SDK errors or credentials."""
    if isinstance(error, TimeoutError):return "timeout", "The LLM check timed out."
    if isinstance(error,(ConnectionError,OSError)):return "network_error", "The check could not connect to the provider."
    # Provider adapters may wrap SDK failures; inspect only bounded structured causes.
    code=None;current=error;seen=set()
    for _ in range(4):
        if current is None or id(current) in seen:break
        seen.add(id(current))
        code=getattr(current,"status_code",None) or getattr(current,"code",None) or getattr(getattr(current,"response",None),"status_code",None)
        if callable(code):code=code()
        if code is not None:break
        current=getattr(current,"__cause__",None) or getattr(current,"__context__",None)
    code=str(getattr(code,"name",code)).upper()
    if code in {"429","RESOURCE_EXHAUSTED"}:return "provider_limit", "The provider reported a quota or rate limit."
    if code in {"401","403","UNAUTHENTICATED","PERMISSION_DENIED"}:return "provider_access", "The provider rejected model or credential access."
    if code in {"404","NOT_FOUND"}:return "model_unavailable", "The configured model was not available to this provider project."
    return "provider_error", "The check did not receive a valid LLM response."


async def check_availability(project_id):
    settings=get_settings()
    await run_in_threadpool(require_engineering,settings,require_principal())
    result={"provider":settings.llm_provider,"model":settings.llm_model,"checked_at":None,
            "provider_invocation_count":0,"retry_after_seconds":0}
    def complete(status,reason,message):
        return {**result,"status":status,"reason":reason,"message":message,"checked_at":datetime.now(UTC).isoformat()}
    try:
        operation=await run_in_threadpool(admission.admit_current,project_id,"diagnostic")
    except HTTPException as error:
        # Ownership failures and missing Engineering grants stay authorization failures.
        if error.status_code in {401,404}:raise
        result["retry_after_seconds"]=int((error.headers or {}).get("Retry-After","0"))
        return complete("blocked","admission_blocked",str(error.detail))
    known_response=False
    try:
        with admission.operation_scope(operation):
            admission.check_input([PROMPT])
            timeout=min(setting_value(settings,"llm_timeout_seconds"),15)
            llm=get_llm(streaming=False,temperature=0,max_output_tokens=min(setting_value(settings,"diagnostic_max_output_tokens"),80),max_retries=0,timeout=timeout)
            result["provider_invocation_count"]=1
            response=await _tracked_diagnostic_invoke(llm,PROMPT,settings.llm_model,project_id=project_id,timeout=timeout)
            known_response=bool(_message_text(response).strip())
            # Arbitrary non-empty answers do not prove the fixed check succeeded.
            if _message_text(response).strip().rstrip(".! ").upper()!="OK":
                return complete("failed","unexpected_response","The LLM returned an unexpected diagnostic response.")
            return complete("reachable","response_received","The last check received a valid Gemini response.")
    except (LLMConfigurationError,HTTPException):
        return complete("blocked","configuration_blocked","Local provider configuration blocked this check.")
    except Exception as error:
        reason,message=provider_failure(error)
        return complete("failed",reason,message)
    finally:
        await run_in_threadpool(admission.finish,operation,known_response=known_response)
