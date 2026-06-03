from typing import Any

from app.models.metrics import (
    MetricCompletenessItem,
    MetricSourceRecord,
    MetricSummaryResponse,
    SaveVerifiedMetricsResponse,
    VerifiedMetricInput,
)
from app.services.storage_service import (
    delete_metric_source_record,
    get_metric_source_record,
    get_project_record,
    list_video_records,
    list_metric_source_records,
    upsert_metric_source_record,
)


class MetricProjectNotFoundError(Exception):
    """Raised when metric source data is requested for a missing project."""


class MetricValidationError(Exception):
    """Raised when verified metric input is invalid."""


class MetricRecordNotFoundError(Exception):
    """Raised when a metric source record cannot be found."""


PUBLIC_YOUTUBE_NOTE = (
    "YouTube counts are extracted from public metadata and may differ slightly "
    "from the live UI because of rounding, caching, timezone, or updates."
)
PUBLIC_INSTAGRAM_NOTE = (
    "Instagram public extraction may exclude Facebook cross-posted reactions, "
    "comments, shares, views, or profile metrics."
)
NO_ESTIMATE_NOTE = "Unavailable metrics are not estimated."
COMBINED_META_NOTE = (
    "Combined Meta Metrics are calculated only from available Instagram native "
    "metrics and verified Facebook cross-post metrics."
)
VERIFIED_METHODS = {"user_verified", "manual_entry", "screenshot_verified"}
VALID_PLATFORMS = {"youtube", "instagram", "facebook", "meta"}
VALID_METHODS = {
    "public_extractor",
    "user_verified",
    "manual_entry",
    "screenshot_verified",
    "meta_api",
    "unavailable",
}
VALID_SCOPES = {"native", "cross_post", "combined", "verified_override"}
METRIC_FIELDS = ["views", "likes", "reactions", "comments", "shares", "followers"]


def ensure_public_metric_records(project_id: str) -> None:
    if get_project_record(project_id) is None:
        raise MetricProjectNotFoundError("Project not found.")

    for video_record in list_video_records(project_id):
        platform = str(video_record.get("platform"))

        if platform == "youtube":
            note = PUBLIC_YOUTUBE_NOTE
            confidence = "medium"
        elif platform == "instagram":
            note = PUBLIC_INSTAGRAM_NOTE
            confidence = _instagram_confidence(video_record)
        elif platform == "facebook":
            note = (
                "Facebook public metrics are extracted when available. Missing "
                "fields are unavailable and not estimated."
            )
            confidence = "low"
        else:
            continue

        upsert_metric_source_record(
            project_id=project_id,
            platform=platform,
            source_platform=platform,
            source_method="public_extractor",
            metric_scope="native",
            url=_string_or_none(video_record.get("url")),
            views=_int_or_none(video_record.get("views")),
            likes=_int_or_none(video_record.get("likes")),
            reactions=_int_or_none(video_record.get("reactions")),
            comments=_int_or_none(video_record.get("comments")),
            shares=_int_or_none(video_record.get("shares")),
            followers=(
                _int_or_none(video_record.get("follower_count"))
                or _int_or_none(video_record.get("subscriber_count"))
            ),
            engagement_rate=_float_or_none(video_record.get("engagement_rate")),
            confidence=confidence,
            note=note,
        )


def save_verified_metrics(
    project_id: str,
    payload: VerifiedMetricInput,
) -> MetricSourceRecord:
    _ensure_project_exists(project_id)
    _validate_metric_input(payload)
    engagement_rate = _engagement_rate_for_payload(payload)
    record = upsert_metric_source_record(
        project_id=project_id,
        platform=payload.platform,
        source_platform=payload.source_platform,
        source_method=payload.source_method,
        metric_scope=payload.metric_scope,
        url=_clean_text(payload.url),
        views=payload.views,
        likes=payload.likes,
        reactions=payload.reactions,
        comments=payload.comments,
        shares=payload.shares,
        followers=payload.followers,
        engagement_rate=engagement_rate,
        confidence=_confidence_for_method(payload.source_method),
        note=_clean_text(payload.note),
    )

    return MetricSourceRecord(**record)


def get_metric_summary(project_id: str) -> MetricSummaryResponse:
    ensure_public_metric_records(project_id)
    records = [
        MetricSourceRecord(**record)
        for record in list_metric_source_records(project_id)
    ]
    youtube_native = _latest_matching(records, "youtube", "native")
    instagram_native = _latest_matching(records, "instagram", "native")
    facebook_crosspost = _latest_matching(records, "facebook", "cross_post")
    completeness = [
        _completeness_item(
            label="YouTube native metrics",
            record=youtube_native,
            required_fields=["views", "likes", "comments"],
            note=PUBLIC_YOUTUBE_NOTE,
        ),
        _completeness_item(
            label="Instagram native metrics",
            record=instagram_native,
            required_fields=["views", "likes", "comments", "followers"],
            note=PUBLIC_INSTAGRAM_NOTE,
        ),
        _completeness_item(
            label="Facebook cross-post metrics",
            record=facebook_crosspost,
            required_fields=["views", "reactions", "comments", "shares"],
            note="Facebook cross-post metrics require user-verified or manual input.",
        ),
    ]
    combined_values = _combined_meta_values(
        instagram_native=instagram_native,
        facebook_crosspost=facebook_crosspost,
    )
    combined_item = MetricCompletenessItem(
        label="Combined Meta Metrics",
        status=combined_values["status"],
        available_fields=combined_values["available_fields"],
        missing_fields=combined_values["missing_fields"],
        note=combined_values["note"],
    )
    completeness.append(combined_item)

    return MetricSummaryResponse(
        project_id=project_id,
        metric_completeness_score=_completeness_score(completeness),
        instagram_native_status=completeness[1].status,
        facebook_crosspost_status=completeness[2].status,
        combined_meta_status=combined_item.status,
        youtube_status=completeness[0].status,
        combined_meta_engagement_rate=combined_values["engagement_rate"],
        combined_meta_interactions=combined_values["interactions"],
        combined_meta_views=combined_values["views"],
        records=records,
        completeness=completeness,
        notes=_summary_notes(facebook_crosspost=facebook_crosspost),
    )


def save_verified_metrics_with_summary(
    project_id: str,
    payload: VerifiedMetricInput,
) -> SaveVerifiedMetricsResponse:
    record = save_verified_metrics(project_id=project_id, payload=payload)
    summary = get_metric_summary(project_id)

    return SaveVerifiedMetricsResponse(
        status="saved",
        record=record,
        summary=summary,
    )


def delete_verified_metric_record(project_id: str, record_id: str) -> None:
    _ensure_project_exists(project_id)

    if get_metric_source_record(project_id=project_id, record_id=record_id) is None:
        raise MetricRecordNotFoundError("Metric source record not found.")

    delete_metric_source_record(project_id=project_id, record_id=record_id)


def _ensure_project_exists(project_id: str) -> None:
    if get_project_record(project_id) is None:
        raise MetricProjectNotFoundError("Project not found.")


def _validate_metric_input(payload: VerifiedMetricInput) -> None:
    if payload.platform not in VALID_PLATFORMS:
        raise MetricValidationError("Platform must be YouTube, Instagram, Facebook, or Meta.")

    if payload.source_platform not in VALID_PLATFORMS:
        raise MetricValidationError("Source platform must be YouTube, Instagram, Facebook, or Meta.")

    if payload.source_method not in VALID_METHODS:
        raise MetricValidationError("Metric source method is not supported.")

    if payload.metric_scope not in VALID_SCOPES:
        raise MetricValidationError("Metric scope is not supported.")

    for field_name in METRIC_FIELDS:
        value = getattr(payload, field_name)

        if value is not None and value < 0:
            raise MetricValidationError(f"{field_name} must not be negative.")


def _engagement_rate_for_payload(payload: VerifiedMetricInput) -> float | None:
    views = payload.views

    if views is None or views <= 0:
        return None

    interactions = _interactions_for_payload(payload)

    if interactions is None:
        return None

    return round((interactions / views) * 100, 2)


def _interactions_for_payload(payload: VerifiedMetricInput) -> int | None:
    if payload.source_platform == "facebook" or payload.metric_scope == "cross_post":
        values = [payload.reactions, payload.comments, payload.shares]
    else:
        values = [payload.likes, payload.comments]

    available_values = [value for value in values if value is not None]

    if not available_values:
        return None

    return sum(available_values)


def _combined_meta_values(
    instagram_native: MetricSourceRecord | None,
    facebook_crosspost: MetricSourceRecord | None,
) -> dict[str, Any]:
    if facebook_crosspost is None:
        return {
            "status": "unavailable",
            "views": None,
            "interactions": None,
            "engagement_rate": None,
            "available_fields": [],
            "missing_fields": ["facebook_crosspost"],
            "note": "Combined Meta Metrics need verified Facebook cross-post metrics.",
        }

    instagram_views = instagram_native.views if instagram_native else None
    facebook_views = facebook_crosspost.views
    instagram_interactions = _record_interactions(
        instagram_native,
        fields=["likes", "comments"],
    )
    facebook_interactions = _record_interactions(
        facebook_crosspost,
        fields=["reactions", "comments", "shares"],
    )
    views = _sum_available([instagram_views, facebook_views])
    interactions = _sum_available([instagram_interactions, facebook_interactions])
    engagement_rate = (
        round((interactions / views) * 100, 2)
        if views is not None and views > 0 and interactions is not None
        else None
    )
    available_fields = []
    missing_fields = []

    for field_name, value in (
        ("instagram_views", instagram_views),
        ("facebook_views", facebook_views),
        ("instagram_interactions", instagram_interactions),
        ("facebook_interactions", facebook_interactions),
        ("combined_meta_engagement_rate", engagement_rate),
    ):
        if value is None:
            missing_fields.append(field_name)
        else:
            available_fields.append(field_name)

    return {
        "status": _status_from_fields(available_fields, missing_fields),
        "views": views,
        "interactions": interactions,
        "engagement_rate": engagement_rate,
        "available_fields": available_fields,
        "missing_fields": missing_fields,
        "note": COMBINED_META_NOTE,
    }


def _completeness_item(
    label: str,
    record: MetricSourceRecord | None,
    required_fields: list[str],
    note: str,
) -> MetricCompletenessItem:
    if record is None:
        return MetricCompletenessItem(
            label=label,
            status="unavailable",
            available_fields=[],
            missing_fields=required_fields,
            note=note,
        )

    available_fields = [
        field_name
        for field_name in required_fields
        if getattr(record, field_name) is not None
    ]
    missing_fields = [
        field_name
        for field_name in required_fields
        if getattr(record, field_name) is None
    ]

    return MetricCompletenessItem(
        label=label,
        status=_status_from_fields(available_fields, missing_fields),
        available_fields=available_fields,
        missing_fields=missing_fields,
        note=note,
    )


def _completeness_score(completeness: list[MetricCompletenessItem]) -> float:
    if not completeness:
        return 0.0

    score = 0.0

    for item in completeness:
        if item.status == "complete":
            score += 1.0
        elif item.status == "partial":
            score += 0.5

    return round((score / len(completeness)) * 100, 2)


def _latest_matching(
    records: list[MetricSourceRecord],
    source_platform: str,
    metric_scope: str,
) -> MetricSourceRecord | None:
    verified_records = [
        record
        for record in records
        if record.source_platform == source_platform
        and record.metric_scope == metric_scope
        and record.source_method in VERIFIED_METHODS
    ]

    if verified_records:
        return verified_records[0]

    for record in records:
        if record.source_platform == source_platform and record.metric_scope == metric_scope:
            return record

    return None


def _status_from_fields(
    available_fields: list[str],
    missing_fields: list[str],
) -> str:
    if available_fields and not missing_fields:
        return "complete"

    if available_fields:
        return "partial"

    return "unavailable"


def _record_interactions(
    record: MetricSourceRecord | None,
    fields: list[str],
) -> int | None:
    if record is None:
        return None

    values = [
        getattr(record, field_name)
        for field_name in fields
        if getattr(record, field_name) is not None
    ]

    if not values:
        return None

    return sum(values)


def _sum_available(values: list[int | None]) -> int | None:
    available_values = [value for value in values if value is not None]

    if not available_values:
        return None

    return sum(available_values)


def _summary_notes(facebook_crosspost: MetricSourceRecord | None) -> list[str]:
    notes = [NO_ESTIMATE_NOTE, PUBLIC_INSTAGRAM_NOTE, COMBINED_META_NOTE]

    if facebook_crosspost is None:
        notes.append(
            "Facebook cross-post metrics are unavailable until the user provides verified values."
        )

    return notes


def _instagram_confidence(record: dict[str, Any]) -> str:
    available_count = sum(
        1
        for field_name in ("views", "likes", "comments", "follower_count")
        if record.get(field_name) is not None
    )

    return "medium" if available_count >= 2 else "low"


def _confidence_for_method(source_method: str) -> str:
    if source_method in VERIFIED_METHODS:
        return "user_verified"

    if source_method == "unavailable":
        return "unavailable"

    return "medium"


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return float(value)

    return None


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    clean_value = value.strip()
    return clean_value if clean_value else None
