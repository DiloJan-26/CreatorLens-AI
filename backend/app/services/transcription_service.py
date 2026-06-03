import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.video import TranscriptSegment


DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_WORDS_PER_SEGMENT = 12


class TranscriptionUnavailableError(Exception):
    """Raised when a transcript cannot be produced for a media item."""


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscriptSegment]
    transcript_language: str | None = None
    detected_language: str | None = None
    language_confidence: float | None = None
    transcript_source: str | None = None
    transcript_source_note: str | None = None


def build_empty_transcript() -> list[TranscriptSegment]:
    return []


def transcript_segments_from_plain_text(text: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []

    for raw_segment in re.findall(r"[^.!?]+(?:[.!?]+|$)", text):
        clean_segment = raw_segment.strip()

        if not clean_segment:
            continue

        segments.append(
            TranscriptSegment(
                segment_index=len(segments),
                start_time=None,
                end_time=None,
                text=clean_segment,
            )
        )

    return segments


def transcribe_audio_url_with_deepgram(audio_url: str) -> TranscriptionResult:
    settings = get_settings()
    api_key = (settings.deepgram_api_key or "").strip()

    if not api_key:
        raise TranscriptionUnavailableError("Deepgram API key is not configured.")

    if not audio_url.strip():
        raise TranscriptionUnavailableError("Audio URL is missing.")

    params = {
        "model": settings.deepgram_model,
        "smart_format": "true",
        "punctuate": "true",
        "paragraphs": "true",
        "utterances": "true",
    }
    configured_language = _configured_deepgram_language(settings.transcript_language)

    if configured_language:
        params["language"] = configured_language
    elif settings.deepgram_detect_language:
        params["detect_language"] = "true"

    headers = {"Authorization": f"Token {api_key}"}
    payload = {"url": audio_url}

    try:
        response = httpx.post(
            DEEPGRAM_LISTEN_URL,
            params=params,
            headers=headers,
            json=payload,
            timeout=httpx.Timeout(45.0, connect=10.0),
        )
        response.raise_for_status()
        response_json = response.json()
    except httpx.HTTPStatusError as exc:
        raise TranscriptionUnavailableError(
            f"Deepgram transcription failed with HTTP {exc.response.status_code}."
        ) from None
    except (httpx.HTTPError, ValueError):
        raise TranscriptionUnavailableError("Deepgram transcription failed.") from None

    if not isinstance(response_json, dict):
        raise TranscriptionUnavailableError(
            "Deepgram transcription returned no usable data."
        )

    segments = deepgram_response_to_segments(response_json)

    if not segments:
        raise TranscriptionUnavailableError(
            "Transcript unavailable or incomplete. The audio may be unsupported, mixed-language, noisy, or not publicly extractable."
        )

    detected_language = _detected_language(response_json) or configured_language
    if configured_language == "multi" and not detected_language:
        detected_language = "multi"
    language_confidence = _language_confidence(response_json)

    return TranscriptionResult(
        segments=segments,
        transcript_language=configured_language or detected_language,
        detected_language=detected_language,
        language_confidence=language_confidence,
        transcript_source="deepgram_multilingual",
        transcript_source_note=_deepgram_source_note(detected_language),
    )


def deepgram_response_to_segments(response_json: dict[str, Any]) -> list[TranscriptSegment]:
    segments = _segments_from_utterances(response_json)

    if segments:
        return segments

    alternative = _first_alternative(response_json)

    if alternative:
        segments = _segments_from_paragraph_sentences(alternative)

        if segments:
            return segments

        words = alternative.get("words")

        if isinstance(words, list):
            segments = _segments_from_words(words)

            if segments:
                return segments

        transcript = alternative.get("transcript")

        if isinstance(transcript, str):
            return transcript_segments_from_plain_text(transcript)

    return []


def transcribe_instagram_audio_url(audio_url: str | None) -> list[TranscriptSegment]:
    if audio_url is None:
        return []

    try:
        return transcribe_audio_url_with_deepgram(audio_url).segments
    except TranscriptionUnavailableError:
        return []


def transcribe_instagram_audio_url_with_metadata(
    audio_url: str | None,
) -> TranscriptionResult:
    if audio_url is None:
        raise TranscriptionUnavailableError(
            "Transcript unavailable because no captions were found and public media audio could not be extracted."
        )

    return transcribe_audio_url_with_deepgram(audio_url)


def _segments_from_utterances(
    response_json: dict[str, Any],
) -> list[TranscriptSegment]:
    results = response_json.get("results")

    if not isinstance(results, dict):
        return []

    utterances = results.get("utterances")

    if not isinstance(utterances, list):
        return []

    segments: list[TranscriptSegment] = []

    for utterance in utterances:
        if not isinstance(utterance, dict):
            continue

        text = _text_value(utterance.get("transcript"))

        if text is None:
            continue

        segments.append(
            TranscriptSegment(
                segment_index=len(segments),
                start_time=_float_value(utterance.get("start")),
                end_time=_float_value(utterance.get("end")),
                text=text,
            )
        )

    return segments


def _segments_from_paragraph_sentences(
    alternative: dict[str, Any],
) -> list[TranscriptSegment]:
    paragraphs = alternative.get("paragraphs")

    if not isinstance(paragraphs, dict):
        return []

    paragraph_items = paragraphs.get("paragraphs")

    if not isinstance(paragraph_items, list):
        return []

    segments: list[TranscriptSegment] = []

    for paragraph in paragraph_items:
        if not isinstance(paragraph, dict):
            continue

        sentences = paragraph.get("sentences")

        if not isinstance(sentences, list):
            continue

        for sentence in sentences:
            if not isinstance(sentence, dict):
                continue

            text = _text_value(sentence.get("text"))

            if text is None:
                continue

            segments.append(
                TranscriptSegment(
                    segment_index=len(segments),
                    start_time=_float_value(sentence.get("start")),
                    end_time=_float_value(sentence.get("end")),
                    text=text,
                )
            )

    return segments


def _segments_from_words(words: list[Any]) -> list[TranscriptSegment]:
    clean_words = [word for word in words if isinstance(word, dict)]
    segments: list[TranscriptSegment] = []
    current_words: list[dict[str, Any]] = []

    for word in clean_words:
        token = _word_text(word)

        if token is None:
            continue

        current_words.append(word)

        if len(current_words) >= DEEPGRAM_WORDS_PER_SEGMENT or token.endswith(
            (".", "?", "!")
        ):
            _append_word_segment(segments, current_words)
            current_words = []

    if current_words:
        _append_word_segment(segments, current_words)

    return segments


def _append_word_segment(
    segments: list[TranscriptSegment],
    words: list[dict[str, Any]],
) -> None:
    text = " ".join(
        token for word in words if (token := _word_text(word)) is not None
    ).strip()

    if not text:
        return

    segments.append(
        TranscriptSegment(
            segment_index=len(segments),
            start_time=_float_value(words[0].get("start")),
            end_time=_float_value(words[-1].get("end")),
            text=text,
        )
    )


def _first_alternative(response_json: dict[str, Any]) -> dict[str, Any] | None:
    results = response_json.get("results")

    if not isinstance(results, dict):
        return None

    channels = results.get("channels")

    if not isinstance(channels, list) or not channels:
        return None

    first_channel = channels[0]

    if not isinstance(first_channel, dict):
        return None

    alternatives = first_channel.get("alternatives")

    if not isinstance(alternatives, list) or not alternatives:
        return None

    first_alternative = alternatives[0]
    return first_alternative if isinstance(first_alternative, dict) else None


def _configured_deepgram_language(value: str) -> str | None:
    language = value.strip().lower() if isinstance(value, str) else ""

    if not language:
        return None

    if language in {"multi", "auto", "multilingual"}:
        return "multi"

    return language


def _detected_language(response_json: dict[str, Any]) -> str | None:
    results = response_json.get("results")

    if not isinstance(results, dict):
        return None

    for key in ("detected_language", "language"):
        value = _text_value(results.get(key))

        if value:
            return value

    channels = results.get("channels")

    if isinstance(channels, list):
        for channel in channels:
            if not isinstance(channel, dict):
                continue

            value = _text_value(channel.get("detected_language")) or _text_value(
                channel.get("language")
            )

            if value:
                return value

            alternatives = channel.get("alternatives")
            if isinstance(alternatives, list):
                for alternative in alternatives:
                    if not isinstance(alternative, dict):
                        continue
                    value = _text_value(
                        alternative.get("detected_language")
                    ) or _text_value(alternative.get("language"))
                    if value:
                        return value

    return None


def _language_confidence(response_json: dict[str, Any]) -> float | None:
    results = response_json.get("results")

    if isinstance(results, dict):
        value = _float_value(
            results.get("language_confidence")
            or results.get("detected_language_confidence")
        )
        if value is not None:
            return value

    alternative = _first_alternative(response_json)
    if alternative:
        return _float_value(
            alternative.get("language_confidence")
            or alternative.get("detected_language_confidence")
        )

    return None


def _deepgram_source_note(detected_language: str | None) -> str:
    if detected_language and detected_language != "multi":
        return (
            "Transcript generated from public media audio using Deepgram multilingual "
            f"transcription. Detected language: {detected_language}."
        )

    if detected_language == "multi":
        return (
            "Transcript language could not be confidently detected; multilingual "
            "transcription was used."
        )

    return (
        "Transcript generated from public media audio using Deepgram multilingual "
        "transcription."
    )


def _word_text(word: dict[str, Any]) -> str | None:
    text = _text_value(word.get("punctuated_word")) or _text_value(word.get("word"))
    return text


def _text_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None
