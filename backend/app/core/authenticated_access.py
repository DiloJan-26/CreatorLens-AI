"""Authenticated application boundary; unknown routes are denied by default."""
import re
from starlette.requests import Request
from fastapi import HTTPException
from app.core.access import provision, owned_project, require_admin, authorize_resource
from app.core.identity import verifier
from app.core.request_limits import enforce_rate
from app.db.session import database_session
from app.db.models.chat import ChatSession
from app.db.models.metric_source import MetricSource
from app.db.models.ingestion_job import IngestionJob


def authenticate_request(scope, settings):
    request = Request(scope)
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401,"Sign in with Google to continue.",headers={"WWW-Authenticate":"Bearer"})
    principal=verifier.verify(token,settings)
    path = request.url.path.rstrip("/")
    enforce_rate(settings,principal.user_id)
    with database_session() as session:
        provision(session,principal)
        match=re.fullmatch(r"/api/projects/([^/]+)(/.*)?",path)
        if match:
            project_id=match[1]; owned_project(session,project_id,principal)
            remainder=match[2] or ""
            nested=re.fullmatch(r"/chat/sessions/([^/]+)",remainder)
            if nested: authorize_resource(session,project_id,ChatSession,nested[1],principal)
            source=re.fullmatch(r"/metrics/sources/([^/]+)",remainder)
            if source: authorize_resource(session,project_id,MetricSource,source[1],principal)
            if path.endswith("/status") and request.query_params.get("job_id"):
                authorize_resource(session,project_id,IngestionJob,request.query_params["job_id"],principal)
            # Direct extraction/reindex aliases cannot bypass analysis admission.
            if request.method not in {"GET","HEAD","OPTIONS"} and remainder in {"/extract","/index","/chunks/build"}:
                raise HTTPException(403,"Use the quota-controlled analysis workflow.")
        elif path == "/api/metrics/cost":
            project_id=request.query_params.get("project_id")
            if project_id: owned_project(session,project_id,principal)
            else: require_admin(session,principal)
        elif path.startswith("/api/evaluations"):
            if path != "/api/evaluations/datasets": require_admin(session,principal)
        elif path.startswith("/health/") or path in {"/docs","/redoc","/openapi.json"}:
            require_admin(session,principal)
            if request.method != "GET" or settings.environment not in {"local","test"} and path in {"/docs","/redoc","/openapi.json"}:
                raise HTTPException(403,"Interactive diagnostics are disabled.")
        elif path not in {"/api/projects","/api/demo/capabilities","/api/account","/api/account/usage","/api/account/logout"}:
            raise HTTPException(404,"Not found.")
    return principal
