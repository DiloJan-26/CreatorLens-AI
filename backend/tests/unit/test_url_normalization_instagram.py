import pytest

from app.services.url_normalization_service import (
    UnsupportedContentUrlError,
    normalize_content_url,
    normalize_instagram_url,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://instagram.com/reel/ABC_123/?igsh=tracking",
            "https://www.instagram.com/reel/ABC_123/",
        ),
        (
            "https://www.instagram.com/p/POST-123#fragment",
            "https://www.instagram.com/p/POST-123/",
        ),
        (
            "https://m.instagram.com/tv/TV_123/",
            "https://www.instagram.com/tv/TV_123/",
        ),
    ],
)
def test_instagram_urls_remove_tracking_and_normalize_host(
    url: str,
    expected: str,
) -> None:
    assert normalize_instagram_url(url) == expected
    assert normalize_content_url(url) == expected


def test_instagram_profile_url_is_not_content() -> None:
    with pytest.raises(UnsupportedContentUrlError):
        normalize_instagram_url("https://www.instagram.com/creatorlens/")
