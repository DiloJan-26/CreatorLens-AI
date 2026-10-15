from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.ingestion import router as ingestion_router
from app.api.insights import router as insights_router
from app.api.metrics import router as metrics_router
from app.api.projects import router as projects_router
from app.core.config import get_settings
from app.services.storage_compat_service import init_db


settings = get_settings()

API_DESCRIPTION = """
CreatorLens AI compares public short-form content and provides evidence-backed
creator insights through metadata extraction, retrieval, and AI-assisted analysis.

## Recommended API workflow

1. Confirm service dependencies under **0. System Readiness**.
2. Create or load a comparison under **1. Projects**.
3. Queue the complete pipeline under **2. Async Ingestion** and poll its status.
4. Use **3. Content Extraction** and **4. Evidence Preparation** only for
   stepwise diagnostics or backward-compatible V1 testing.
5. Inspect retrieval/context under **5. Retrieval & Context**.
6. Review verified metrics and deterministic insights under sections **6–7**.
7. Create a session and ask cited questions under sections **8–9**.

Use the `project_id` returned when creating a project in all subsequent project
routes. Evidence must be built and indexed before retrieval-backed chat can
return useful citations.

### ⚠️ Brave Browser Notice

When testing CreatorLens API endpoints through Swagger UI in **Brave Browser**,
Brave Shields may block some requests, particularly health checks, and cause
Swagger to show **“Failed to fetch”** with CORS or network-related warnings.

If this occurs:

1. Open the CreatorLens Swagger `/docs` page in Brave.
2. Click the **Brave Shields / lion icon** in the address bar.
3. Turn **Shields OFF for this site only**.
4. Refresh Swagger UI; use a hard refresh (`Ctrl + Shift + R`) if needed.
5. Retry the API request.

This is caused by Brave's browser-side privacy protections and does **not
necessarily indicate a CreatorLens API CORS configuration problem**. Google
Chrome can access these Swagger endpoints without this Brave-specific adjustment.
"""


OPENAPI_TAGS = [
    {
        "name": "0. System Readiness",
        "description": (
            "Start here. Check the API process and its Qdrant, embedding, and "
            "Gemini dependencies before running a full analysis. Generation test "
            "routes may consume provider quota."
        ),
    },
    {
        "name": "1. Projects",
        "description": (
            "Create a two-content comparison and obtain its `project_id`, or load "
            "an existing project. The returned ID is required by later sections."
        ),
    },
    {
        "name": "2. Async Ingestion",
        "description": (
            "Recommended analysis path. Queue the complete extraction, chunking, "
            "embedding, and indexing pipeline, then poll its persisted job status."
        ),
    },
    {
        "name": "3. Content Extraction",
        "description": (
            "Backward-compatible stepwise extraction diagnostics. Normal UI flows "
            "should use Async Ingestion; these routes remain available for inspection."
        ),
    },
    {
        "name": "4. Evidence Preparation",
        "description": (
            "Convert extracted content into evidence chunks, inspect those chunks, "
            "and index them in Qdrant. Recommended order: build → inspect → index."
        ),
    },
    {
        "name": "5. Retrieval & Context",
        "description": (
            "Test semantic retrieval and preview the complete context that cited "
            "chat will send to the language model. Requires indexed evidence."
        ),
    },
    {
        "name": "6. Verified Metrics",
        "description": (
            "Review metric provenance and optionally store or remove user-verified "
            "metrics. Missing public metrics remain unavailable rather than inferred."
        ),
    },
    {
        "name": "7. Creator Insights",
        "description": (
            "Generate the deterministic comparison summary used by the Insights UI "
            "from persisted metadata, transcripts, and verified metrics."
        ),
    },
    {
        "name": "8. Chat Sessions",
        "description": (
            "Create, reload, or delete persisted project chat sessions before using "
            "the streaming AI chat endpoint."
        ),
    },
    {
        "name": "9. AI Chat",
        "description": (
            "Stream an evidence-backed answer with citations. Create a chat session "
            "and index project evidence first. The stream uses Server-Sent Events."
        ),
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="CreatorLens AI API",
    description=API_DESCRIPTION,
    version="0.1.0",
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={
        "docExpansion": "list",
        "filter": True,
        "displayRequestDuration": True,
    },
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(ingestion_router)
app.include_router(chat_router)
app.include_router(metrics_router)
app.include_router(insights_router)
