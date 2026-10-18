from types import SimpleNamespace

import httpx
import pytest

from app.services import supadata_transcript_service
from app.services.supadata_transcript_service import (
    SupadataTranscriptUnavailableError,
    transcribe_video_url_with_supadata,
)


def test_supadata_converts_timestamped_chunks_to_seconds(monkeypatch) -> None:
    monkeypatch.setattr(
        supadata_transcript_service,
        "get_settings",
        lambda: SimpleNamespace(
            supadata_api_key="test-key",
            supadata_transcript_mode="native",
            supadata_transcript_timeout_seconds=60,
        ),
    )
    monkeypatch.setattr(
        supadata_transcript_service,
        "_fetch_transcript_payload",
        lambda **_kwargs: {
            "lang": "en",
            "content": [
                {"text": "First segment", "offset": 0, "duration": 1500},
                {"text": "Second segment", "offset": 1500, "duration": 2000},
            ],
        },
    )

    result = transcribe_video_url_with_supadata(
        "https://www.youtube.com/watch?v=example"
    )

    assert result.transcript_source == "supadata_platform_captions"
    assert result.transcript_language == "en"
    assert len(result.segments) == 2
    assert result.segments[0].start_time == 0.0
    assert result.segments[0].end_time == 1.5
    assert result.segments[1].start_time == 1.5
    assert result.segments[1].end_time == 3.5


def test_supadata_requires_an_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        supadata_transcript_service,
        "get_settings",
        lambda: SimpleNamespace(
            supadata_api_key=None,
            supadata_transcript_mode="native",
            supadata_transcript_timeout_seconds=60,
        ),
    )

    with pytest.raises(SupadataTranscriptUnavailableError):
        transcribe_video_url_with_supadata(
            "https://www.youtube.com/watch?v=example"
        )


def test_supadata_rejects_empty_transcript_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        supadata_transcript_service,
        "get_settings",
        lambda: SimpleNamespace(
            supadata_api_key="test-key",
            supadata_transcript_mode="native",
            supadata_transcript_timeout_seconds=60,
        ),
    )
    monkeypatch.setattr(
        supadata_transcript_service,
        "_fetch_transcript_payload",
        lambda **_kwargs: {"lang": "en", "content": []},
    )

    with pytest.raises(SupadataTranscriptUnavailableError):
        transcribe_video_url_with_supadata(
            "https://www.youtube.com/watch?v=example"
        )


def test_supadata_sends_api_key_in_header_not_request_url(monkeypatch) -> None:
    api_key = "supadata-secret-key"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "lang": "en",
                "content": [
                    {"text": "Transcript", "offset": 0, "duration": 1000}
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        supadata_transcript_service.httpx,
        "Client",
        lambda **_: real_client(transport=transport),
    )

    payload = supadata_transcript_service._fetch_transcript_payload(
        url="https://www.youtube.com/watch?v=example",
        api_key=api_key,
        mode="native",
        timeout_seconds=60,
    )

    assert payload["lang"] == "en"
    assert len(requests) == 1
    assert api_key not in str(requests[0].url)
    assert requests[0].headers["x-api-key"] == api_key
