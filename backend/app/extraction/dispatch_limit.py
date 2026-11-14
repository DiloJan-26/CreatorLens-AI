"""Shared provider request pacing; Redis failure cannot enable extraction."""
from hashlib import sha256
import time
from app.core.request_limits import client
from app.extraction.policy import ExtractionSafetyError


def enforce_provider_rate(settings, *, connection=None):
    # Published prepaid Free: 1 request/s; monthly Pro: 10 requests/s.
    interval = 1100 if settings.supadata_billing_tier == "free_prepaid" else 110
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
