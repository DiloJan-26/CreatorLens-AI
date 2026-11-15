"""Shared provider request pacing; Redis failure cannot enable extraction."""
from app.core.config import setting_value
from hashlib import sha256
import time
from app.core.request_limits import client
from app.extraction.policy import ExtractionSafetyError


def enforce_provider_rate(settings, *, connection=None):
    # Published prepaid Free: 1 request/s; monthly Pro: 10 requests/s.
    minimum = {"free_prepaid":1000,"pro_monthly_prepaid":100}.get(settings.supadata_billing_tier)
    if getattr(settings,"extraction_active_pricing_json",None) is not None:
        from decimal import Decimal,ROUND_CEILING
        from app.extraction.policy import configuration
        prices=configuration(settings)
        verified_rate=min(Decimal(p["max_requests_per_second"]) for p in prices)
        minimum=int((Decimal(1000)/verified_rate).to_integral_value(rounding=ROUND_CEILING))
    interval = setting_value(settings,'supadata_request_interval_ms')
    if minimum is None or interval < minimum:
        raise ExtractionSafetyError("Approved provider pacing is unavailable or exceeds the supported tier limit.")
    deadline = time.monotonic() + settings.extraction_timeout_seconds
    key = "creatorlens:provider-pace:" + sha256(settings.supadata_credit_pool.encode()).hexdigest()
    try:
        redis = connection or client(settings.redis_url)
        while time.monotonic() < deadline:
            if redis.set(key, "busy", nx=True, px=interval):
                return
            time.sleep(min(.1, max(0, deadline-time.monotonic())))
    except Exception:
        raise ExtractionSafetyError("Provider pacing admission is unavailable; no external request sent.") from None
    raise ExtractionSafetyError("Provider pacing deadline reached; no external request sent.")
