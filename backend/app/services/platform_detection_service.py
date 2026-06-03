from typing import Literal
from urllib.parse import urlparse


DetectedPlatform = Literal["youtube", "instagram", "facebook"]


class UnsupportedPlatformUrlError(ValueError):
    """Raised when a URL is not supported by public content extraction."""


UNSUPPORTED_URL_MESSAGE = (
    "Unsupported URL. Please use a YouTube Short, Instagram Reel, or "
    "Facebook Reel/post video URL."
)


def detect_platform(url: str) -> DetectedPlatform:
    parsed = urlparse(url.strip())
    host = _normalized_host(parsed.netloc)
    path = parsed.path.lower()
    path_parts = [part for part in path.split("/") if part]

    if parsed.scheme not in {"http", "https"} or not host:
        raise UnsupportedPlatformUrlError(UNSUPPORTED_URL_MESSAGE)

    if host in {"youtube.com", "m.youtube.com"} or host.endswith(".youtube.com"):
        if path.startswith("/shorts/") or path == "/watch":
            return "youtube"

    if host == "youtu.be" and path.strip("/"):
        return "youtube"

    if host == "instagram.com" or host.endswith(".instagram.com"):
        if path_parts and path_parts[0] in {"reel", "p", "tv"}:
            return "instagram"

    if host == "fb.watch" and path.strip("/"):
        return "facebook"

    if host == "facebook.com" or host.endswith(".facebook.com"):
        if path.startswith("/reel/") or path.startswith("/watch"):
            return "facebook"

        if len(path_parts) >= 2 and path_parts[1] == "videos":
            return "facebook"

        if len(path_parts) >= 3 and path_parts[0] == "share" and path_parts[1] == "r":
            return "facebook"

    raise UnsupportedPlatformUrlError(UNSUPPORTED_URL_MESSAGE)


def _normalized_host(host: str) -> str:
    clean_host = host.lower().strip()

    if clean_host.startswith("www."):
        return clean_host[4:]

    return clean_host
