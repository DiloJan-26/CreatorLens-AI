from typing import Literal

from pydantic import BaseModel


MetricSourceMethod = Literal[
    "public_extractor",
    "user_verified",
    "manual_entry",
    "screenshot_verified",
    "meta_api",
    "unavailable",
]
MetricSourcePlatform = Literal["youtube", "instagram", "facebook", "meta"]
MetricScope = Literal["native", "cross_post", "combined", "verified_override"]


class MetricSourceRecord(BaseModel):
    id: str
    project_id: str
    platform: str
    source_platform: str
    source_method: str
    metric_scope: str
    url: str | None = None
    views: int | None = None
    likes: int | None = None
    reactions: int | None = None
    comments: int | None = None
    shares: int | None = None
    followers: int | None = None
    engagement_rate: float | None = None
    confidence: str
    note: str | None = None
    created_at: str
    updated_at: str


class VerifiedMetricInput(BaseModel):
    platform: MetricSourcePlatform
    source_platform: MetricSourcePlatform
    metric_scope: MetricScope
    source_method: MetricSourceMethod = "user_verified"
    url: str | None = None
    views: int | None = None
    likes: int | None = None
    reactions: int | None = None
    comments: int | None = None
    shares: int | None = None
    followers: int | None = None
    note: str | None = None


class MetricCompletenessItem(BaseModel):
    label: str
    status: str
    available_fields: list[str]
    missing_fields: list[str]
    note: str | None = None


class MetricSummaryResponse(BaseModel):
    project_id: str
    metric_completeness_score: float
    instagram_native_status: str
    facebook_crosspost_status: str
    combined_meta_status: str
    youtube_status: str
    combined_meta_engagement_rate: float | None = None
    combined_meta_interactions: int | None = None
    combined_meta_views: int | None = None
    records: list[MetricSourceRecord]
    completeness: list[MetricCompletenessItem]
    notes: list[str]


class SaveVerifiedMetricsResponse(BaseModel):
    status: str
    record: MetricSourceRecord
    summary: MetricSummaryResponse
