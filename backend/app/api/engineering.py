"""Authenticated Engineering access and an explicit, bounded provider diagnostic."""
import json
from fastapi import APIRouter, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from app.core.access import require_principal
from app.core.config import get_settings
from app.core.engineering_access import access_status, unlock, lock

router = APIRouter(prefix='/api/engineering', tags=['Engineering access'])


@router.get('/access')
def status(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    return access_status(get_settings(), require_principal())


@router.post('/unlock')
async def unlock_access(request: Request, response: Response):
    # Bounded parsing avoids validation responses echoing a submitted secret.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 2048: raise HTTPException(413, 'Unlock request is too large.')
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or set(payload) != {'access_key'} or not isinstance(payload['access_key'], str) or len(payload['access_key']) > 256:
            raise ValueError('Invalid payload')
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(400, 'Enter a valid Engineering access key.') from None
    response.headers['Cache-Control'] = 'private, no-store'
    return await run_in_threadpool(unlock, get_settings(), require_principal(), payload['access_key'])


@router.post('/lock')
def lock_access(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    return lock(get_settings(), require_principal())


from uuid import UUID
from pydantic import BaseModel, ConfigDict


class LlmCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: UUID


@router.post('/llm-check')
async def llm_check(payload: LlmCheckRequest, response: Response):
    from app.services.llm_diagnostic_service import check_availability
    response.headers['Cache-Control'] = 'private, no-store'
    return await check_availability(str(payload.project_id))
