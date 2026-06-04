# ── Stage 1: dependencies ────────────────────────────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /app

# System packages needed at install time (some fastembed wheels require gcc)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# ffmpeg  → yt-dlp needs it to mux audio/video streams
# curl    → useful for ad-hoc health checks inside the container
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ffmpeg \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the build stage
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source
COPY app/ app/

# Pre-download the embedding model so the first request is instant.
# The model (~130 MB) is baked into this layer; no network call at runtime.
RUN python -c "\
from fastembed import TextEmbedding; \
model = TextEmbedding(model_name='BAAI/bge-small-en-v1.5'); \
_ = list(model.embed(['warmup'])); \
print('Embedding model pre-loaded.')"

# Create the storage directory used by SQLite (paths.py → BACKEND_ROOT/storage)
RUN mkdir -p /app/storage

# Render injects a $PORT env var; default to 8000 for local Docker runs.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
