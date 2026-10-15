"""Deterministic SHA-256 helpers for content cache identities."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Any


def hash_text(value: str) -> str:
    """Hash text exactly as supplied using a lowercase SHA-256 digest."""
    if not isinstance(value, str):
        raise TypeError("Hash text must be a string.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json(value: Any) -> str:
    """Serialize supported values deterministically before hashing."""
    normalized = _normalize_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def hash_payload(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-like value."""
    return hash_text(stable_json(value))


def hash_metadata(metadata: Mapping[str, Any]) -> str:
    """Hash the caller-selected metadata fields deterministically."""
    return hash_payload(metadata)


def hash_transcript(segments: Sequence[Mapping[str, Any]]) -> str:
    """Hash ordered transcript segments deterministically."""
    return hash_payload(segments)


def hash_chunk(text: str) -> str:
    """Hash the exact chunk text independently of project ownership."""
    return hash_text(text)


def hash_content(*, metadata_hash: str, transcript_hash: str | None) -> str:
    """Build one content identity from its metadata and transcript identities."""
    return hash_payload(
        {
            "metadata_hash": metadata_hash,
            "transcript_hash": transcript_hash,
        }
    )


def hash_embedding(
    *,
    chunk_hash: str,
    model_name: str,
    model_version: str,
) -> str:
    """Build an embedding compatibility identity without storing vector data."""
    return hash_payload(
        {
            "chunk_hash": chunk_hash,
            "model_name": model_name,
            "model_version": model_version,
        }
    )


def _normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | bool):
        return value

    if isinstance(value, float):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Enum):
        return _normalize_value(value.value)

    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Hash payload mapping keys must be strings.")
            normalized[key] = _normalize_value(item)
        return normalized

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_normalize_value(item) for item in value]

    raise TypeError(f"Unsupported hash payload type: {type(value).__name__}.")
