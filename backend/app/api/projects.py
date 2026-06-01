from fastapi import APIRouter, Query, status

from app.models.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectListResponse,
    ProjectRecord,
)
from app.services.project_service import create_project, get_project, list_projects


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


@router.get("/{project_id}", response_model=ProjectRecord)
def get_project_endpoint(project_id: str) -> ProjectRecord:
    return get_project(project_id)
