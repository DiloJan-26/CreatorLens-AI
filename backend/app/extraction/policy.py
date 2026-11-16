"""Bounded extraction and optional, historical Supadata pricing metadata."""
from app.core.config import setting_value
from datetime import date, datetime, UTC
from decimal import Decimal, ROUND_UP
from hashlib import sha256
import json
from pathlib import Path
import re
from fastapi import HTTPException
from app.services.url_normalization_service import normalize_content_url

POLICY_VERSION = "bounded-native-1.0.0"
SLOTS = {"content_1", "content_2"}


class ExtractionSafetyError(RuntimeError):
    """Sanitized failure; provider results must not be silently discarded."""


def registry(path=None):
    if path is None:
        from app.core.config import get_settings
        from app.core.active_pricing import active_registry
        value = getattr(get_settings(), "extraction_active_pricing_json", None)
        if value is not None:
            return active_registry(value, "extraction")
    data = json.loads(Path(path or Path(__file__).with_name("pricing_registry.json")).read_text(encoding="utf-8"))
    return validate_registry(data)


def validate_registry(data):
    periods = {}
    for entry in data["entries"]:
        start, end = date.fromisoformat(entry["effective_from"]), date.fromisoformat(entry["effective_through"])
        price = Decimal(entry["subscription_usd"])
        if start > end or not price.is_finite() or price < 0 or entry["included_credits"] <= 0 or entry["quantity_per_request"] != 1:
            raise ValueError("Invalid extraction pricing interval or quantity.")
        key = (entry["provider"], entry["operation"], entry["tier"])
        if any(start <= b and a <= end for a, b in periods.get(key, [])):
            raise ValueError("Overlapping extraction prices.")
        periods.setdefault(key, []).append((start, end))
    return data


def price_for(operation, tier, *, provider="supadata", at=None, data=None):
    at = at or datetime.now(UTC).date()
    data = data or registry()
    entry = next((e for e in data["entries"] if e["provider"] == provider and e["operation"] == operation and e["tier"] == tier and date.fromisoformat(e["effective_from"]) <= at <= date.fromisoformat(e["effective_through"])), None)
    if entry is None:
        raise HTTPException(403, "Verified provider-specific operation/tier/date pricing is unavailable.")
    result = dict(entry, pricing_policy=entry.get("pricing_policy", data["policy_version"]))
    result["allocated_unit_usd"] = str((Decimal(entry["subscription_usd"]) / entry["included_credits"]).quantize(Decimal(".000000000001"), rounding=ROUND_UP))
    result["estimate_basis"] = "allocated_prepaid_subscription"
    return result


def configuration(settings, *, at=None):
    """Validate bounded execution; provider account plans are not app entitlements."""
    if getattr(settings,"provider_emergency_stop",True):
        raise HTTPException(403,"External provider execution is suspended.")
    if not (getattr(settings,"supadata_api_key",None) or "").strip():
        raise HTTPException(403,"SUPADATA_API_KEY is required for extraction.")
    if getattr(settings,"supadata_transcript_mode","native") != "native":
        raise HTTPException(403,"Only native caption extraction is supported.")
    for name in ("extraction_max_concurrent_operations", "extraction_max_video_seconds", "extraction_max_url_bytes", "extraction_max_response_bytes", "extraction_timeout_seconds", "paid_requests_per_minute"):
        if not getattr(settings,name,0):
            raise HTTPException(403,"Nonzero extraction bounds and rate limits are required.")
    bounds=[Decimal(getattr(settings,name,"0")) for name in ("provider_operation_ceiling_usd","user_budget_usd","global_budget_usd")]
    if any(not value.is_finite() or value<=0 for value in bounds):
        raise HTTPException(403,"Nonzero operation and user/global budget bounds are required.")
    if setting_value(settings,'supadata_request_interval_ms') < 1000:
        raise HTTPException(403,"Supadata requests must be paced at no more than one per second.")


def observed_price(settings, operation):
    """Optional local cost metadata, never an execution prerequisite or zero fallback."""
    try:
        from app.core.active_pricing import active_registry
        raw=getattr(settings,"extraction_active_pricing_json",None)
        data=active_registry(raw,"extraction") if raw is not None else registry(Path(__file__).with_name("pricing_registry.json"))
        return price_for(operation,getattr(settings,"supadata_billing_tier",""),data=data)
    except (HTTPException, ValueError, KeyError, TypeError):
        return None


def input_url(url, platform, settings):
    if not isinstance(url, str) or len(url.encode("utf-8")) > settings.extraction_max_url_bytes:
        raise ExtractionSafetyError("Video URL exceeds the approved input bound.")
    from urllib.parse import urlsplit, parse_qs
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port or parsed.hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com", "m.facebook.com"}:
        raise ExtractionSafetyError("Only HTTPS public video hosts without credentials or ports are permitted.")
    try:
        if platform == "facebook":
            parts = [part for part in parsed.path.split("/") if part]
            identifier = parse_qs(parsed.query).get("v", [""])[0] if parsed.path.rstrip("/") == "/watch" else parts[-1] if parts and (parts[0] == "reel" or "videos" in parts) else ""
            if not re.fullmatch(r"[0-9]+", identifier):
                raise ValueError("Not a Facebook video.")
            normalized = "https://www.facebook.com/watch/?v=" + identifier
        else:
            normalized = normalize_content_url(url)
    except ValueError:
        raise ExtractionSafetyError("Only canonical supported public video URLs are permitted.") from None
    # Normalization verifies exact hosts and video identifiers, never downloads media.
    host = urlsplit(normalized).hostname or ""
    actual = "youtube" if host in {"youtube.com", "www.youtube.com"} else "instagram" if host in {"instagram.com", "www.instagram.com"} else "facebook" if host in {"facebook.com", "www.facebook.com"} else None
    if actual != platform:
        raise ExtractionSafetyError("Platform and canonical URL disagree.")
    return normalized


def checked_duration(value, settings):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 < value <= settings.extraction_max_video_seconds:
        raise ExtractionSafetyError("Provider-verified video duration is missing, invalid or exceeds the approved limit.")
    import math
    if not math.isfinite(value):
        raise ExtractionSafetyError("Invalid video duration.")
    return value


def source_key(user_id, url):
    return sha256((user_id + "\n" + url).encode()).hexdigest()


def block_legacy_provider():
    raise ExtractionSafetyError("Legacy/unbounded provider execution is unavailable; use admitted bounded extraction.")
