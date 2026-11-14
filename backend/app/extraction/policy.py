"""Fixed-credit prepaid exposure, independent of Gemini token pricing.

USD values are allocated subscription estimates, not marginal tariffs or invoices.
A verified, dedicated account with auto-recharge OFF is a prerequisite.
"""
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
    data = json.loads(Path(path or Path(__file__).with_name("pricing_registry.json")).read_text(encoding="utf-8"))
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
    result = dict(entry, pricing_policy=data["policy_version"])
    result["allocated_unit_usd"] = str((Decimal(entry["subscription_usd"]) / entry["included_credits"]).quantize(Decimal(".000000000001"), rounding=ROUND_UP))
    result["estimate_basis"] = "allocated_prepaid_subscription"
    return result


def configuration(settings, *, at=None):
    def deny():
        raise HTTPException(403, "Approved provider-specific prepaid pricing, account verification, credit pool, duration, size and time bounds are required for extraction.")
    if not getattr(settings, "extraction_enabled", False) or not settings.paid_operations_enabled:
        deny()
    if not getattr(settings, "supadata_prepaid_verified", False) or not getattr(settings, "supadata_auto_recharge_disabled", False) or not getattr(settings, "supadata_api_key", None):
        deny()
    if getattr(settings, "supadata_transcript_mode", "native") != "native":
        deny()
    for name in ("extraction_max_concurrent_operations", "extraction_max_video_seconds", "extraction_max_url_bytes", "extraction_max_response_bytes", "extraction_timeout_seconds", "supadata_credit_limit", "paid_requests_per_minute"):
        if not getattr(settings, name, 0):
            deny()
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", getattr(settings, "supadata_credit_pool", "")):
        deny()
    bounds = [Decimal(getattr(settings, name, "0")) for name in ("provider_operation_ceiling_usd", "user_budget_usd", "global_budget_usd")]
    if any(not n.is_finite() or n <= 0 for n in bounds):
        deny()
    prices = [price_for(op, settings.supadata_billing_tier, at=at) for op in ("metadata", "native_transcript")]
    if settings.supadata_credit_limit > min(p["included_credits"] for p in prices) or bounds[0] < max(Decimal(p["allocated_unit_usd"]) for p in prices):
        deny()
    return prices


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
    from app.core.config import get_settings
    if get_settings().application_access_mode == "authenticated":
        raise ExtractionSafetyError("Unbounded legacy provider execution is disabled in authenticated mode.")
