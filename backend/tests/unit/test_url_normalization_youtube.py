import pytest

from app.services.url_normalization_service import (
    UnsupportedContentUrlError,
    normalize_content_url,
    normalize_youtube_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=AbC_123-xYz&utm_source=test",
        "https://youtu.be/AbC_123-xYz?t=30",
        "https://m.youtube.com/shorts/AbC_123-xYz?feature=share",
        "https://www.youtube.com/embed/AbC_123-xYz#fragment",
    ],
)
def test_youtube_variants_share_one_canonical_url(url: str) -> None:
    expected = "https://www.youtube.com/watch?v=AbC_123-xYz"
    assert normalize_youtube_url(url) == expected
    assert normalize_content_url(url) == expected


def test_youtube_url_requires_a_video_identifier() -> None:
    with pytest.raises(UnsupportedContentUrlError):
        normalize_youtube_url("https://www.youtube.com/watch")


def test_youtube_identifier_cannot_inject_query_parameters() -> None:
    with pytest.raises(UnsupportedContentUrlError):
        normalize_youtube_url("https://www.youtube.com/watch?v=video%26admin=true")
