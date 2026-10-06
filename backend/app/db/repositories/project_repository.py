from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models.project import Project
from app.db.repositories._utils import iso_timestamp, utc_now


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        project_id: str,
        content_1_url: str,
        content_2_url: str,
        content_1_platform: str,
        content_2_platform: str,
        status: str,
        youtube_url: str | None = None,
        instagram_url: str | None = None,
    ) -> dict[str, Any]:
        timestamp = utc_now()
        project = Project(
            id=project_id,
            content_1_url=content_1_url,
            content_2_url=content_2_url,
            content_1_platform=content_1_platform,
            content_2_platform=content_2_platform,
            youtube_url=youtube_url,
            instagram_url=instagram_url,
            status=status,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add(project)
        self.session.flush()
        return self.to_record(project)

    def get(self, project_id: str) -> dict[str, Any] | None:
        project = self.session.get(Project, project_id)
        return self.to_record(project) if project is not None else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        projects = self.session.scalars(
            select(Project).order_by(desc(Project.created_at)).limit(safe_limit)
        ).all()
        return [self.to_record(project) for project in projects]

    def update_status(self, project_id: str, status: str) -> bool:
        project = self.session.get(Project, project_id)
        if project is None:
            return False
        project.status = status
        project.updated_at = utc_now()
        self.session.flush()
        return True

    @staticmethod
    def to_record(project: Project) -> dict[str, Any]:
        return {
            "project_id": project.id,
            "content_1_url": project.content_1_url,
            "content_2_url": project.content_2_url,
            "content_1_platform": project.content_1_platform,
            "content_2_platform": project.content_2_platform,
            "youtube_url": project.youtube_url,
            "instagram_url": project.instagram_url,
            "status": project.status,
            "created_at": iso_timestamp(project.created_at),
            "updated_at": iso_timestamp(project.updated_at),
        }
