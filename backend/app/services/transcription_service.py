import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.models.video import TranscriptSegment


DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_WORDS_PER_SEGMENT = 12


class TranscriptionUnavailableError(Exception):
    """Raised when a transcript cannot be produced for a media item."""


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


def transcribe_audio_url_with_deepgram(audio_url: str) -> list[TranscriptSegment]:
    api_key = (get_settings().deepgram_api_key or "").strip()

    if not api_key:
        raise TranscriptionUnavailableError("Deepgram API key is not configured.")

    if not audio_url.strip():
        raise TranscriptionUnavailableError("Audio URL is missing.")

    params = {
        "model": "nova-2",
        "smart_format": "true",
        "punctuate": "true",
        "paragraphs": "true",
        "utterances": "true",
    }
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

    return deepgram_response_to_segments(response_json)


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
        return transcribe_audio_url_with_deepgram(audio_url)
    except TranscriptionUnavailableError:
        return []


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
