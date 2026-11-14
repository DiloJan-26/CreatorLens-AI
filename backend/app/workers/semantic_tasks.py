from app.workers.owned_execution import owned_task
"""Optional post-ingestion semantic task on the existing Celery worker."""
from app.workers.celery_app import celery_app
from app.services.semantic_service import process_semantic_snapshot

@celery_app.task(name='creatorlens.semantic_features', max_retries=0)
@owned_task("semantic")
def extract_semantic_features(snapshot_id: str):
    from app.core.demo_access import require_local_worker
    require_local_worker()
    return process_semantic_snapshot(snapshot_id)
