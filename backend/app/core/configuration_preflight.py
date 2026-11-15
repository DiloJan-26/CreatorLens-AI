"""Offline configuration review. Never connects, prints secrets or changes settings."""
import argparse
from hashlib import sha256
import json
from app.core.config import Settings
from app.core.model_policy import model_configuration_error

SHARED_FIELDS = (
    "llm_provider", "llm_model", "semantic_supported_languages",
    "celery_queue", "initial_free_analyses", "concurrent_analyses_per_user",
    "assistant_admissions_per_analysis", "semantic_attempts_per_slot",
    "extraction_metadata_attempts_per_slot", "extraction_transcript_attempts_per_slot",
    "paid_requests_per_minute", "provider_input_byte_limit", "provider_schema_token_allowance",
    "user_budget_usd", "global_budget_usd", "provider_operation_ceiling_usd",
    "provider_emergency_stop", "extraction_max_concurrent_operations",
    "extraction_max_video_seconds", "extraction_max_url_bytes", "extraction_max_response_bytes",
    "extraction_timeout_seconds", "supadata_billing_tier", "supadata_prepaid_verified",
    "supadata_auto_recharge_disabled", "supadata_credit_pool_cap", "supadata_credit_limit",
    "supadata_request_interval_ms", "llm_estimate_service_tier", "llm_cache_billing_mode",
    "llm_max_output_tokens", "assistant_max_output_tokens", "semantic_max_output_tokens",
    "llm_timeout_seconds", "semantic_timeout_seconds", "inference_deadline_grace_seconds",
    "qdrant_collection", "embedding_model_name", "embedding_model_version",
    "evidence_cache_max_age_seconds", "transcript_language", "transcript_fallback_languages",
)
# Private configuration is hashed, never printed. Matching hashes are only a
# consistency aid; they do not establish authorization, account balance or health.
PRIVATE_SHARED_FIELDS = (
    "database_url", "redis_url", "celery_broker_url", "celery_result_backend",
    "llm_active_pricing_json", "extraction_active_pricing_json", "supadata_credit_pool",
    "qdrant_url", "qdrant_api_key", "gemini_api_key", "supadata_api_key",
)


def audit(settings, *, release=False):
    errors=[]
    if release:
        if settings.environment != "production":errors.append("ENVIRONMENT must be production.")
        try:settings.require_service_configuration()
        except ValueError:errors.append("Trusted authentication, database, Redis and API-origin settings are required.")
        if not settings.provider_emergency_stop:errors.append("Initial release requires PROVIDER_EMERGENCY_STOP=true.")
        if not settings.analysis_requests_per_minute:errors.append("ANALYSIS_REQUESTS_PER_MINUTE requires a reviewed nonzero value.")
        if not settings.authenticated_requests_per_minute:errors.append("AUTHENTICATED_REQUESTS_PER_MINUTE requires a reviewed nonzero value.")
        error=model_configuration_error(settings)
        if error:errors.append(error)
        if not settings.qdrant_url or not settings.qdrant_api_key:errors.append("QDRANT_URL and QDRANT_API_KEY must identify the existing private vector service.")
    shared={name:str(getattr(settings,name)) for name in SHARED_FIELDS+PRIVATE_SHARED_FIELDS}
    fingerprint=sha256(json.dumps(shared,sort_keys=True).encode()).hexdigest()
    return {"status":"FAIL" if errors else "PASS","errors":errors,"shared_configuration_sha256":fingerprint,
            "verification":"configuration only; no service connectivity or provider-account verification"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",action="store_true")
    args=parser.parse_args()
    try:
        result=audit(Settings(),release=args.release)
    except Exception:
        result={"status":"FAIL","errors":["Settings validation failed; review required keys privately. Values deliberately omitted."]}
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result["status"]=="PASS" else 1)


if __name__=="__main__":main()
