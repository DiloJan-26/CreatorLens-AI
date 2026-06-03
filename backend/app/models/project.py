from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.video import Platform, VideoMetadata


ProjectStatus = Literal["created", "extracting", "ready", "failed"]


class ProjectCreateRequest(BaseModel):
    content_1_url: str | None = Field(default=None, min_length=1)
    content_2_url: str | None = Field(default=None, min_length=1)
    youtube_url: str | None = Field(default=None, min_length=1)
    instagram_url: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_two_urls(self) -> "ProjectCreateRequest":
        content_1_url = self.content_1_url or self.youtube_url
        content_2_url = self.content_2_url or self.instagram_url

        if not content_1_url or not content_2_url:
            raise ValueError(
                "Provide Content URL 1 and Content URL 2."
            )

        self.content_1_url = content_1_url
        self.content_2_url = content_2_url
        return self


class ProjectCreateResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    message: str


class ProjectRecord(BaseModel):
    project_id: str
    content_1_url: str
    content_2_url: str
    content_1_platform: Platform
    content_2_platform: Platform
    youtube_url: str | None = None
    instagram_url: str | None = None
    status: ProjectStatus
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectRecord]


class ProjectDetailResponse(BaseModel):
    project_id: str
    content_1_url: str
    content_2_url: str
    content_1_platform: Platform
    content_2_platform: Platform
    youtube_url: str | None = None
    instagram_url: str | None = None
    status: ProjectStatus
    created_at: str
    updated_at: str
    content_items: list[VideoMetadata] = Field(default_factory=list)
    youtube: VideoMetadata | None = None
    instagram: VideoMetadata | None = None


class MetadataAvailabilityItem(BaseModel):
    slot: str
    platform: Platform
    url: str
    available_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    completeness_score: float
    note: str


class MetadataAvailabilityResponse(BaseModel):
    project_id: str
    items: list[MetadataAvailabilityItem] = Field(default_factory=list)
