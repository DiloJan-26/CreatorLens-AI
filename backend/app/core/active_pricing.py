"""Operator-approved active registry selection; bundled files remain immutable archives.

Approval is an operator attestation, not independent online tariff verification.
An active registry is a complete authority for new calculations: no archive fallback
on missing model, tier or period. Existing stored quotes are never recalculated.
"""
from datetime import date
import json
from urllib.parse import urlsplit
from hashlib import sha256


def active_registry(raw: str, kind: str) -> dict:
    try:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 65536:
            raise ValueError()
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        envelope = json.loads(raw, object_pairs_hook=unique_pairs)
        if set(envelope) != {"approval","registry"}:
            raise ValueError()
        approval = envelope["approval"]
        if set(approval) != {"approved","approved_by","approved_on","change_reference"}:
            raise ValueError()
        if approval.get("approved") is not True:
            raise ValueError()
        for key in ("approved_by", "change_reference", "approved_on"):
            if not isinstance(approval.get(key), str) or not 1 <= len(approval[key].strip()) <= 200:
                raise ValueError()
        date.fromisoformat(approval["approved_on"])
        data = envelope["registry"]
        entries = data["entries"]
        version_key = "version" if kind == "llm" else "policy_version"
        if not isinstance(data.get(version_key), str) or not data[version_key].strip() or not 0 < len(entries) <= 100:
            raise ValueError()
        if set(data) != {version_key,"entries"}:
            raise ValueError()
        for entry in entries:
            allowed={"provider","model","service_tier","policy_version","api_backend","currency","effective_from","effective_until","verified_on","source_url","resolved_source_url","token_categories","input_per_million","output_per_million","cached_input_per_million"} if kind=="llm" else {"provider","operation","endpoint","tier","billing_unit","quantity_per_request","currency","subscription_usd","included_credits","effective_from","effective_through","verified_on","source_url","pricing_policy","max_requests_per_second"}
            if set(entry)-allowed:
                raise ValueError()
            source = urlsplit(entry["source_url"])
            hosts = {"ai.google.dev", "aistudio.google.com"} if kind == "llm" else {"supadata.ai", "docs.supadata.ai"}
            if source.scheme != "https" or source.hostname not in hosts or source.username or source.password or source.port or source.query:
                raise ValueError()
            if entry.get("currency") != "USD":
                raise ValueError()
            date.fromisoformat(entry["verified_on"])
            if kind == "llm":
                from app.core.model_policy import require_supported_model
                require_supported_model(entry["model"])
                if entry["provider"] != "gemini" or entry["api_backend"] != "gemini_developer_api" or entry["service_tier"] != "standard":
                    raise ValueError()
                if entry.get("token_categories") != ["uncached_input", "cached_input", "output_including_thinking"]:
                    raise ValueError()
                for key in ("input_per_million", "output_per_million", "cached_input_per_million"):
                    if not isinstance(entry[key], str) or len(entry[key]) > 32:
                        raise ValueError()
                    from decimal import Decimal
                    amount=Decimal(entry[key])
                    if not amount.is_finite() or not 0 <= amount <= Decimal("1000000000") or amount.as_tuple().exponent < -12:
                        raise ValueError()
            else:
                endpoints = {"metadata": "/v1/metadata", "native_transcript": "/v1/transcript"}
                if entry["tier"] not in {"free_prepaid","pro_monthly_prepaid"} or entry["provider"] != "supadata" or entry.get("endpoint") != endpoints.get(entry["operation"]) or entry.get("billing_unit") != "credit":
                    raise ValueError()
                if type(entry["included_credits"]) is not int or not isinstance(entry["subscription_usd"], str):
                    raise ValueError()
                from decimal import Decimal
                rate=Decimal(entry["max_requests_per_second"])
                if not isinstance(entry["max_requests_per_second"],str) or len(entry["max_requests_per_second"]) > 32 or not rate.is_finite() or not Decimal("0.01") <= rate <= 10000 or rate.as_tuple().exponent < -6:
                    raise ValueError()
                if not isinstance(entry.get("pricing_policy"), str) or not entry["pricing_policy"]:
                    raise ValueError()
        if kind == "llm":
            from app.llm.pricing_policy import validate_registry
        else:
            from app.extraction.policy import validate_registry
        validate_registry(data)
        # A published policy identity cannot be reused for a changed archived rate.
        from pathlib import Path
        archive=json.loads((Path(__file__).resolve().parents[1]/("llm" if kind=="llm" else "extraction")/"pricing_registry.json").read_text(encoding="utf-8"))
        policy_key="policy_version" if kind=="llm" else "pricing_policy"
        identity=("provider","model","service_tier","api_backend") if kind=="llm" else ("provider","operation","tier")
        fields=identity+(("effective_from","effective_until","input_per_million","output_per_million","cached_input_per_million") if kind=="llm" else ("effective_from","effective_through","subscription_usd","included_credits","quantity_per_request","endpoint","billing_unit"))
        for entry in entries:
            for previous in archive["entries"]:
                if previous.get(policy_key)==entry[policy_key] and all(previous.get(k)==entry.get(k) for k in identity):
                    if any(previous.get(k)!=entry.get(k) for k in fields):
                        raise ValueError()
        # Copy approval provenance into every quote; rate/version persists with the operation.
        digest = sha256(raw.encode("utf-8")).hexdigest()
        for entry in entries:
            entry["operator_approval"] = dict(approval)
            entry["configuration_sha256"] = digest
        return data
    except Exception:
        raise ValueError("Active pricing requires a valid, approved, non-overlapping USD registry with supported identities and provenance.") from None
