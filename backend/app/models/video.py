from typing import Literal

from pydantic import BaseModel, Field


Platform = Literal["youtube", "instagram", "facebook"]
ContentSlot = Literal["content_1", "content_2"]
ExtractionStatus = Literal["pending", "extracting", "ready", "partial", "failed"]


class TranscriptSegment(BaseModel):
    segment_index: int
    start_time: float | None = None
    end_time: float | None = None
    text: str


class VideoMetadata(BaseModel):
    slot: ContentSlot | None = None
    platform: Platform
    url: str
    title: str | None = None
    creator_handle: str | None = None
    description: str | None = None
    caption: str | None = None
    creator: str | None = None
    follower_count: int | None = None
    subscriber_count: int | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    reactions: int | None = None
    shares: int | None = None
    hashtags: list[str] = Field(default_factory=list)
    upload_date: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    media_url: str | None = None
    audio_url: str | None = None
    engagement_rate: float | None = None
    missing_fields: list[str] = Field(default_factory=list)
    transcript_available: bool = False
    transcript_segment_count: int = 0
    extraction_status: ExtractionStatus = "pending"
    error_message: str | None = None
    metric_source_note: str | None = None
    transcript_source_note: str | None = None


class VideoExtractionResult(BaseModel):
    metadata: VideoMetadata
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)


class TranscriptPreviewResponse(BaseModel):
    project_id: str
    slot: ContentSlot | None = None
    platform: Platform
    transcript_available: bool
    transcript_segment_count: int
    segments: list[TranscriptSegment] = Field(default_factory=list)
