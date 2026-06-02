from fastapi import APIRouter, Query, status

from app.models.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectDetailResponse,
    ProjectListResponse,
)
from app.services.project_service import (
    create_project,
    extract_project_videos,
    get_project_detail,
    list_projects,
)


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post(
    "",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project_endpoint(
    payload: ProjectCreateRequest,
) -> ProjectCreateResponse:
    return create_project(payload)


@router.get("", response_model=ProjectListResponse)
def list_projects_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
) -> ProjectListResponse:
    return list_projects(limit=limit)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
def get_project_endpoint(project_id: str) -> ProjectDetailResponse:
    return get_project_detail(project_id)


@router.post("/{project_id}/extract", response_model=ProjectDetailResponse)
def extract_project_endpoint(project_id: str) -> ProjectDetailResponse:
    return extract_project_videos(project_id)
