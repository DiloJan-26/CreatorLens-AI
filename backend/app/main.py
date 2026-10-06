from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.insights import router as insights_router
from app.api.metrics import router as metrics_router
from app.api.projects import router as projects_router
from app.core.config import get_settings
from app.services.storage_compat_service import init_db


settings = get_settings()

API_DESCRIPTION = """
CreatorLens AI compares public short-form content and provides evidence-backed
creator insights through metadata extraction, retrieval, and AI-assisted analysis.

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="CreatorLens AI API",
    description=API_DESCRIPTION,
    version="0.1.0",
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
app.include_router(chat_router)
app.include_router(metrics_router)
app.include_router(insights_router)
