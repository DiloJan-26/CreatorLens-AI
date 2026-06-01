from typing import Literal

from pydantic import BaseModel, Field


ProjectStatus = Literal["created", "extracting", "ready", "failed"]


class ProjectCreateRequest(BaseModel):
    youtube_url: str = Field(..., min_length=1)
    instagram_url: str = Field(..., min_length=1)


class ProjectCreateResponse(BaseModel):
    project_id: str
    status: ProjectStatus
    message: str


class ProjectRecord(BaseModel):
    project_id: str
    youtube_url: str
    instagram_url: str
    status: ProjectStatus
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    projects: list[ProjectRecord]
