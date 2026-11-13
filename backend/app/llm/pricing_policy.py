"""Reviewed exact-model, tier and effective-period selection. Never network-fetched."""
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name('pricing_registry.json')


def load_pricing_registry(path: Path | None = None) -> dict:
    registry = json.loads((path or REGISTRY_PATH).read_text(encoding='utf-8'))
    if not isinstance(registry.get('version'), str) or not isinstance(registry.get('entries'), list):
        raise ValueError('Invalid pricing registry.')
    periods: dict[tuple, list[tuple[date, date]]] = {}
    for entry in registry['entries']:
        for key in ('provider', 'model', 'service_tier', 'policy_version',
                    'source_url', 'verified_on', 'api_backend'):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ValueError('Incomplete pricing identity.')
        start = date.fromisoformat(entry['effective_from'])
        end = date.fromisoformat(entry['effective_until']) if entry['effective_until'] else date.max
        date.fromisoformat(entry['verified_on'])
        if start >= end:
            raise ValueError('Invalid effective period.')
        for key in ('input_per_million', 'output_per_million', 'cached_input_per_million'):
            value = Decimal(entry[key])
            if not value.is_finite() or value < 0:
                raise ValueError('Invalid token rate.')
        identity = tuple(entry[k] for k in ('provider', 'model', 'service_tier', 'api_backend'))
        for earlier_start, earlier_end in periods.setdefault(identity, []):
            if start < earlier_end and earlier_start < end:
                raise ValueError('Overlapping pricing periods.')
        periods[identity].append((start, end))
    return registry


def pricing_date(at: date | datetime | None) -> date:
    if at is None:
        return datetime.now(UTC).date()
    if isinstance(at, datetime):
        if at.tzinfo is None:
            raise ValueError('Inference timestamp requires a timezone.')
        return at.astimezone(UTC).date()
    if isinstance(at, date):
        return at  # Explicit reviewed offline calculations may use a date.
    raise ValueError('Invalid pricing observation date.')


def resolve_price(registry: dict, provider: str, model: str, tier: str | None,
                  day: date, backend: str = 'gemini_developer_api') -> dict | None:
    matches = [row for row in registry['entries']
               if row['provider'] == provider and row['model'] == model
               and row['service_tier'] == tier and row['api_backend'] == backend
               and row['effective_from'] <= day.isoformat()
               and (row['effective_until'] is None or day.isoformat() < row['effective_until'])]
    if len(matches) > 1:
        raise ValueError('Ambiguous pricing selection.')
    return matches[0] if matches else None
