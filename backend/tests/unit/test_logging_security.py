import logging

import httpx

from app.core.logging import SecretRedactionFilter, redact_sensitive_text
from app.extractors import youtube_extractor


def test_redacts_configured_secrets_and_common_credential_shapes() -> None:
    secret = "configured-secret-value"
    message = (
        "secret=configured-secret-value "
        "url=https://user:password@example.com/path?key=query-secret "
        "Authorization: Bearer bearer-secret "
        "X-Goog-Api-Key: header-secret"
    )

    redacted = redact_sensitive_text(message, secret_values=[secret])

    for sensitive_value in (
        secret,
        "user:password",
        "query-secret",
        "bearer-secret",
        "header-secret",
    ):
        assert sensitive_value not in redacted
    assert redacted.count("[redacted]") == 5


def test_log_filter_redacts_values_supplied_as_format_arguments() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request key=%s",
        args=("configured-secret-value",),
        exc_info=None,
    )

    assert SecretRedactionFilter(["configured-secret-value"]).filter(record)
    assert record.getMessage() == "request key=[redacted]"


def test_youtube_api_key_is_sent_in_header_not_request_url(monkeypatch) -> None:
    api_key = "youtube-secret-key"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/videos"):
            payload = {
                "items": [
                    {
                        "snippet": {
                            "title": "Video",
                            "channelId": "channel-1",
                            "channelTitle": "Creator",
                        },
                        "statistics": {},
                        "contentDetails": {"duration": "PT1M"},
                    }
                ]
            }
        else:
            payload = {"items": [{"statistics": {"subscriberCount": "42"}}]}
        return httpx.Response(200, request=request, json=payload)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(
        youtube_extractor.httpx,
        "Client",
        lambda **_: real_client(transport=transport),
    )

    info = youtube_extractor.fetch_youtube_info_from_api("video-1", api_key)

    assert info["subscriber_count"] == 42
    assert len(requests) == 2
    for request in requests:
        assert api_key not in str(request.url)
        assert "key" not in request.url.params
        assert request.headers["X-Goog-Api-Key"] == api_key
