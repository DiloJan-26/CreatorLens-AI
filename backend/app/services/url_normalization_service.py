"""Canonical URL helpers used to build stable content cache keys."""

import re
from urllib.parse import ParseResult, parse_qs, urlparse


class UnsupportedContentUrlError(ValueError):
    """Raised when a URL cannot be normalized as a supported content URL."""


def normalize_content_url(url: str) -> str:
    """Return the canonical URL for a supported YouTube, Instagram or Facebook video."""
    parsed = _parse_http_url(url)
    host = _normalized_host(parsed.hostname)

    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return normalize_youtube_url(url)

    if host == "instagram.com" or host.endswith(".instagram.com"):
        return normalize_instagram_url(url)

    if host in {"facebook.com", "m.facebook.com"}:
        return normalize_facebook_url(url)

    raise UnsupportedContentUrlError("Use a YouTube, Instagram or Facebook video URL.")


def normalize_youtube_url(url: str) -> str:
    """Normalize supported YouTube URL variants to a canonical watch URL."""
    parsed = _parse_http_url(url)
    host = _normalized_host(parsed.hostname)
    path_parts = [part for part in parsed.path.split("/") if part]
    video_id: str | None = None

    if host == "youtu.be" and path_parts:
        video_id = path_parts[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if parsed.path.rstrip("/") == "/watch":
            video_ids = parse_qs(parsed.query).get("v", [])
            video_id = video_ids[0] if video_ids else None
        elif len(path_parts) >= 2 and path_parts[0].lower() in {
            "embed",
            "live",
            "shorts",
        }:
            video_id = path_parts[1]
    else:
        raise UnsupportedContentUrlError("The URL is not a YouTube URL.")

    clean_video_id = _required_path_identifier(video_id, platform="YouTube")
    return f"https://www.youtube.com/watch?v={clean_video_id}"


def normalize_instagram_url(url: str) -> str:
    """Normalize supported Instagram post, reel, and TV URLs."""
    parsed = _parse_http_url(url)
    host = _normalized_host(parsed.hostname)

    if host != "instagram.com" and not host.endswith(".instagram.com"):
        raise UnsupportedContentUrlError("The URL is not an Instagram URL.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) < 2 or path_parts[0].lower() not in {"p", "reel", "tv"}:
        raise UnsupportedContentUrlError(
            "The Instagram URL must identify a post, reel, or TV item."
        )

    content_type = path_parts[0].lower()
    shortcode = _required_path_identifier(path_parts[1], platform="Instagram")
    return f"https://www.instagram.com/{content_type}/{shortcode}/"


def normalize_facebook_url(url: str) -> str:
    """Canonicalize public video identities without following shortened share redirects."""
    parsed = _parse_http_url(url)
    if _normalized_host(parsed.hostname) not in {"facebook.com", "m.facebook.com"}:
        raise UnsupportedContentUrlError("The URL is not a Facebook video URL.")
    parts = [p for p in parsed.path.split("/") if p]
    identifier = parse_qs(parsed.query).get("v", [""])[0] if parsed.path.rstrip("/") == "/watch" else parts[-1] if parts and (parts[0] == "reel" or "videos" in parts) else ""
    if not re.fullmatch(r"[0-9]+", identifier):
        raise UnsupportedContentUrlError("Copy the Facebook Reel, watch or page video URL instead of a shortened share link.")
    return "https://www.facebook.com/watch/?v=" + identifier


def _parse_http_url(url: str) -> ParseResult:
    if not isinstance(url, str) or not url.strip():
        raise UnsupportedContentUrlError("A non-empty content URL is required.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname is None:
        raise UnsupportedContentUrlError("The content URL must use HTTP or HTTPS.")

    return parsed


def _normalized_host(host: str | None) -> str:
    if host is None:
        return ""
    return host.lower().removeprefix("www.")


def _required_path_identifier(value: str | None, *, platform: str) -> str:
    identifier = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
        raise UnsupportedContentUrlError(f"The {platform} content identifier is missing.")
    return identifier
