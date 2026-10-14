from __future__ import annotations

from typing import Any

from sqlalchemy import case, delete, select
from sqlalchemy.orm import Session

from app.db.models.evidence_chunk import EvidenceChunk
from app.db.repositories._utils import utc_now
from app.models.rag import RagChunk


class EvidenceChunkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace(self, project_id: str, chunks: list[RagChunk]) -> None:
        reusable_point_ids = {
            (
                chunk.slot,
                chunk.platform,
                chunk.source_type,
                chunk.chunk_index,
                chunk.embedding_hash,
            ): chunk.qdrant_point_id
            for chunk in self.session.scalars(
                select(EvidenceChunk).where(EvidenceChunk.project_id == project_id)
            ).all()
            if chunk.embedding_hash and chunk.qdrant_point_id
        }
        self.session.execute(
            delete(EvidenceChunk).where(EvidenceChunk.project_id == project_id)
        )
        timestamp = utc_now()
        self.session.add_all(
            [
                EvidenceChunk(
                    id=chunk.chunk_id,
                    project_id=chunk.project_id,
                    content_item_id=chunk.content_id,
                    slot=chunk.slot,
                    platform=chunk.platform,
                    source_type=chunk.source_type,
                    chunk_index=chunk.chunk_index,
                    start_time=chunk.start_time,
                    end_time=chunk.end_time,
                    title=chunk.title,
                    creator=chunk.creator,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    chunk_hash=chunk.chunk_hash,
                    embedding_hash=chunk.embedding_hash,
                    embedding_model_name=chunk.embedding_model_name,
                    embedding_model_version=chunk.embedding_model_version,
                    citation_label=chunk.citation_label,
                    qdrant_point_id=(
                        chunk.qdrant_point_id
                        or reusable_point_ids.get(
                            (
                                chunk.slot,
                                chunk.platform,
                                chunk.source_type,
                                chunk.chunk_index,
                                chunk.embedding_hash,
                            )
                        )
                    ),
                    created_at=timestamp,
                )
                for chunk in chunks
            ]
        )
        self.session.flush()

    def list(
        self, project_id: str, platform: str | None = None
    ) -> list[dict[str, Any]]:
        slot_order = case(
            (EvidenceChunk.slot == "content_1", 0),
            (EvidenceChunk.slot == "content_2", 1),
            else_=2,
        )
        platform_order = case(
            (EvidenceChunk.platform == "youtube", 0),
            (EvidenceChunk.platform == "instagram", 1),
            else_=2,
        )
        statement = select(EvidenceChunk).where(
            EvidenceChunk.project_id == project_id
        )
        if platform is not None:
            statement = statement.where(EvidenceChunk.platform == platform)
        chunks = self.session.scalars(
            statement.order_by(slot_order, platform_order, EvidenceChunk.chunk_index)
        ).all()
        return [self.to_record(chunk) for chunk in chunks]

    def update_qdrant_point_id(self, chunk_id: str, point_id: str) -> bool:
        chunk = self.session.get(EvidenceChunk, chunk_id)
        if chunk is None:
            return False
        chunk.qdrant_point_id = point_id
        self.session.flush()
        return True

    def reusable_point_ids(
        self, embedding_hashes: list[str]
    ) -> dict[str, str]:
        if not embedding_hashes:
            return {}
        chunks = self.session.scalars(
            select(EvidenceChunk).where(
                EvidenceChunk.embedding_hash.in_(embedding_hashes),
                EvidenceChunk.qdrant_point_id.is_not(None),
            )
        ).all()
        return {
            str(chunk.embedding_hash): str(chunk.qdrant_point_id)
            for chunk in chunks
            if chunk.embedding_hash and chunk.qdrant_point_id
        }

    @staticmethod
    def to_record(chunk: EvidenceChunk) -> dict[str, Any]:
        return {
            "chunk_id": chunk.id,
            "project_id": chunk.project_id,
            "content_id": chunk.content_item_id,
            "slot": chunk.slot,
            "platform": chunk.platform,
            "source_type": chunk.source_type,
            "chunk_index": chunk.chunk_index,
            "start_time": chunk.start_time,
            "end_time": chunk.end_time,
            "title": chunk.title,
            "creator": chunk.creator,
            "text": chunk.text,
            "content_hash": chunk.content_hash,
            "chunk_hash": chunk.chunk_hash,
            "embedding_hash": chunk.embedding_hash,
            "embedding_model_name": chunk.embedding_model_name,
            "embedding_model_version": chunk.embedding_model_version,
            "citation_label": chunk.citation_label,
            "qdrant_point_id": chunk.qdrant_point_id,
        }
