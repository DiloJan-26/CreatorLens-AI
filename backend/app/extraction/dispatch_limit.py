"""Shared provider request pacing; Redis failure cannot enable extraction."""
from app.core.config import setting_value
import time
from app.core.request_limits import client
from app.extraction.policy import ExtractionSafetyError


def enforce_provider_rate(settings, *, connection=None):
    # Shared conservative pacing without operator-entered provider plan claims.
    interval = setting_value(settings,'supadata_request_interval_ms')
    if interval < 1000:
        raise ExtractionSafetyError("Supadata requests must be paced at no more than one per second.")
    deadline = time.monotonic() + settings.extraction_timeout_seconds
    key = "creatorlens:provider-pace:supadata"
    try:
        redis = connection or client(settings.redis_url)
        while time.monotonic() < deadline:
            if redis.set(key, "busy", nx=True, px=interval):
                return
            time.sleep(min(.1, max(0, deadline-time.monotonic())))
    except Exception:
        raise ExtractionSafetyError("Provider pacing admission is unavailable; no external request sent.") from None
    raise ExtractionSafetyError("Provider pacing deadline reached; no external request sent.")
