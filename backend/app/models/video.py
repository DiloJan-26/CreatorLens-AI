from typing import Literal

from pydantic import BaseModel, Field


Platform = Literal["youtube", "instagram"]
ExtractionStatus = Literal["pending", "extracting", "ready", "failed"]


class TranscriptSegment(BaseModel):
    segment_index: int
    start_time: float | None = None
    end_time: float | None = None
    text: str


class VideoMetadata(BaseModel):
    platform: Platform
    url: str
    title: str | None = None
    creator: str | None = None
    follower_count: int | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    hashtags: list[str] = Field(default_factory=list)
    upload_date: str | None = None
    duration_seconds: int | None = None
    engagement_rate: float | None = None
    transcript_available: bool = False
    transcript_segment_count: int = 0
    extraction_status: ExtractionStatus = "pending"
    error_message: str | None = None


class VideoExtractionResult(BaseModel):
    metadata: VideoMetadata
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
