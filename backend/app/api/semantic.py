from fastapi import APIRouter, HTTPException
from app.services.semantic_service import get_semantic_analysis, queue_semantic_analysis

router = APIRouter(prefix='/api/projects/{project_id}/semantic', tags=['Creator Semantic Features'])

def _call(operation, project_id, slot, **kwargs):
    try:
        return operation(project_id, slot, **kwargs)
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError:
        raise HTTPException(422, 'Invalid semantic input or evidence.') from None
    except Exception:
        raise HTTPException(503, 'Semantic storage unavailable.') from None

@router.get('/{slot}')
def read_semantic(project_id: str, slot: str):
    return _call(get_semantic_analysis, project_id, slot)

@router.post('/{slot}', status_code=202, description='Explicitly queue optional Gemini analysis; may incur provider charges. No inference occurs in GET.')
def queue_semantic(project_id: str, slot: str, allow_inference: bool = False, retry_failed: bool = False, recover_stale: bool = False):
    if not allow_inference:
        raise HTTPException(422, 'Explicit allow_inference=true is required to queue Gemini analysis.')
    return _call(queue_semantic_analysis, project_id, slot, retry_failed=retry_failed, recover_stale=recover_stale)
