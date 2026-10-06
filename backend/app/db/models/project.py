from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    content_1_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_2_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_1_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    content_2_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    youtube_url: Mapped[str | None] = mapped_column(Text)
    instagram_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
