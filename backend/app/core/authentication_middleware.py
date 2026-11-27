"""Permanent authenticated API boundary; process health is the sole public API."""
from starlette.responses import JSONResponse
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.core.config import get_settings
from app.core.access import current_principal
from app.core.authenticated_access import authenticate_request


class AuthenticationMiddleware:
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope["type"] not in {"http","websocket"}:
            return await self.app(scope,receive,send)
        if scope["type"]=="websocket":
            return await send({"type":"websocket.close","code":1008})
        if scope["path"]=="/health" and scope["method"] in {"GET","HEAD"}:
            return await JSONResponse({"status":"ok","service":"creatorlens-api"})(scope,receive,send)
        try:
            principal=await run_in_threadpool(authenticate_request,scope,get_settings())
        except HTTPException as exc:
            return await JSONResponse({"detail":exc.detail},status_code=exc.status_code,headers={**(exc.headers or {}),"Cache-Control":"private, no-store"})(scope,receive,send)
        scope["state"]={**scope.get("state",{}),"principal":principal}
        token=current_principal.set(principal)
        async def private_send(message):
            if message['type']=='http.response.start' and (scope['path'].startswith(('/api/engineering/','/api/evaluations')) or scope['path']=='/api/metrics/cost'):
                message={**message,'headers':[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'cache-control']+[(b'cache-control',b'private, no-store')]}
            await send(message)
        try:return await self.app(scope,receive,private_send)
        finally:current_principal.reset(token)
