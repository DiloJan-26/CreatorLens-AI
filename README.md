# CreatorLens AI

CreatorLens AI is a full-stack RAG creator intelligence application that compares two public short-form content URLs and turns confirmed metadata, transcript evidence, vector retrieval, and streaming AI chat into actionable creator insights.

The product is built for a technical screening challenge where every output must be dynamic, evidence-backed, and defensible. Users provide two URLs, CreatorLens AI extracts public video evidence, computes engagement metrics, builds a cited vector evidence index, and lets creators ask comparative questions through a streaming RAG chat interface.

```text
Content URL 1 + Content URL 2
        -> platform detection
        -> metadata + transcript extraction
        -> transcript completeness checks
        -> chunking + embeddings
        -> Qdrant vector index
        -> Creator Insight Summary
        -> streaming cited RAG chat
```

## Live Demo

| Surface | URL |
| --- | --- |
| Frontend | https://creator-lens-ai.vercel.app/ |
| Backend | https://creatorlens-ai.onrender.com |
| API docs | https://creatorlens-ai.onrender.com/docs |
| Health | https://creatorlens-ai.onrender.com/health |

## What This Project Proves

| Requirement | Implementation |
| --- | --- |
| Full-stack app | Next.js frontend + FastAPI backend |
| RAG chatbot | LangChain chat flow with retrieval context and memory |
| Embeddings | FastEmbed with `BAAI/bge-small-en-v1.5` |
| Vector DB | Qdrant Cloud with chunk payload filters |
| Streaming responses | Server-sent events from FastAPI to the chat UI |
| Citations | Backend-generated citations for metadata, hook, transcript, and description chunks |
| Two video comparison | Universal Content 1 / Content 2 workflow |
| Dynamic outputs | Extracted from live/public evidence, not hard-coded |
| Metadata extraction | Views, likes/reactions, comments, creator, follower/subscriber count, hashtags, upload date, duration when publicly available |
| Engagement rate | `(likes + comments) / views * 100` for YouTube/Instagram-style metrics; platform-specific interaction handling for Facebook |
| Transcript extraction | YouTube captions, Apify fallback, yt-dlp audio fallback, Deepgram multilingual transcription where applicable |
| Evidence quality | Missing metrics remain unavailable and are not estimated |

## Supported Inputs

| Platform | Supported URL types | Evidence strategy |
| --- | --- | --- |
| YouTube | Shorts, public watch URLs, `youtu.be` URLs | YouTube Data API metadata, captions, Apify transcript fallback, yt-dlp audio fallback |
| Instagram | Reels, posts, TV URLs | Public extraction and Deepgram transcription when public audio is available |
| Facebook | Reels, watch URLs, public post video URLs | Public extraction and Deepgram transcription when public audio is available |

Supported comparisons:

- YouTube vs YouTube
- YouTube vs Instagram
- YouTube vs Facebook
- Instagram vs Instagram
- Instagram vs Facebook
- Facebook vs Facebook

## Tech Stack

| Layer | Technology | Reason |
| --- | --- | --- |
| Frontend | Next.js, React, TypeScript | Fast full-stack UI, App Router, deploys cleanly on Vercel |
| Backend | FastAPI, Python | Strong API ergonomics, async streaming, clean service boundaries |
| RAG orchestration | LangChain | Required by challenge and useful for model abstraction |
| LLM | Gemini Flash through `langchain-google-genai` | Low-cost streaming reasoning for demo scale |
| Embeddings | FastEmbed `BAAI/bge-small-en-v1.5` | Open-source, local embedding generation, avoids per-token embedding cost |
| Vector DB | Qdrant Cloud | Payload filtering by project, slot, platform, and source type |
| Storage | PostgreSQL, SQLAlchemy, Alembic | Durable relational persistence with versioned migrations; SQLite remains an explicit no-`DATABASE_URL` compatibility fallback |
| Async processing | Celery + Upstash Redis | Durable background ingestion with persisted PostgreSQL job status |
| Transcript fallback | `youtube-transcript-api`, Apify, yt-dlp, Deepgram | Layered extraction because social platforms are unreliable from cloud IPs |
| Deployment | Vercel frontend + Render API + Azure Container Apps worker | Separates HTTP traffic from long-running extraction and indexing work |

## High-Level Architecture

```mermaid
flowchart LR
    U[Creator / Interviewer] --> FE[Next.js Frontend]
    FE --> API[FastAPI Backend]

    API --> JOB[(PostgreSQL Ingestion Job)]
    API --> REDIS[(Upstash Redis Queue)]
    REDIS --> WORKER[Azure Celery Worker]
    WORKER --> DETECT[Platform Detection]
    DETECT --> YT[YouTube Extractor]
    DETECT --> IG[Instagram Extractor]
    DETECT --> FB[Facebook Extractor]

    YT --> META[Normalized Metadata]
    IG --> META
    FB --> META

    YT --> TRANS[Transcript Segments]
    IG --> TRANS
    FB --> TRANS

    META --> STORE[(PostgreSQL Project Store)]
    TRANS --> STORE

    STORE --> CHUNK[Chunk Builder]
    CHUNK --> EMBED[FastEmbed BGE Embeddings]
    EMBED --> QDRANT[(Qdrant Vector DB)]

    STORE --> INSIGHTS[Creator Insight Summary]
    QDRANT --> RAG[LangChain RAG Chat]
    STORE --> RAG
    RAG --> SSE[Streaming SSE + Citations]
    SSE --> FE
```

## Low-Level Backend Flow

```mermaid
sequenceDiagram
    participant UI as Next.js UI
    participant API as FastAPI
    participant Q as Upstash Redis
    participant W as Azure Celery Worker
    participant EX as Extractors
    participant DB as PostgreSQL
    participant CB as Chunk Builder
    participant EMB as FastEmbed
    participant VDB as Qdrant
    participant LLM as Gemini via LangChain

    UI->>API: POST /api/projects
    API->>DB: create project
    UI->>API: POST /api/projects/{id}/ingest
    API->>DB: create durable ingestion job
    API->>Q: queue job
    Q->>W: deliver job
    W->>EX: detect platform + extract evidence
    EX-->>W: metadata + transcript segments
    W->>DB: persist metadata, transcript, and job progress
    W->>CB: build metadata, hook, description, transcript chunks
    CB->>EMB: embed chunk text
    EMB-->>W: vectors
    W->>VDB: upsert vectors with payloads
    loop until terminal status
        UI->>API: GET /api/projects/{id}/status
        API-->>UI: stage + progress percentage
    end
    UI->>API: POST /api/projects/{id}/chat/stream
    API->>VDB: retrieve relevant chunks
    API->>DB: load structured metadata and memory
    API->>LLM: prompt with retrieved evidence
    LLM-->>UI: streamed tokens + citations
```

## Extraction Pipeline

CreatorLens AI treats extraction as an engineering problem, not a single API call. Public social platforms are inconsistent, and cloud IPs can be blocked by transcript endpoints. The pipeline is deliberately layered.

```mermaid
flowchart TD
    URL[Input URL] --> DETECT[Detect platform]
    DETECT --> META[Extract confirmed public metadata]
    META --> CAPTIONS{Captions available?}
    CAPTIONS -- yes --> COMPLETE{Transcript covers video duration?}
    CAPTIONS -- no --> APIFY[Apify YouTube transcript fallback]
    COMPLETE -- yes --> SAVE[Save transcript segments]
    COMPLETE -- no --> APIFY
    APIFY --> APIFY_OK{Usable full transcript?}
    APIFY_OK -- yes --> SAVE
    APIFY_OK -- no --> AUDIO[yt-dlp audio URL fallback]
    AUDIO --> DEEPGRAM[Deepgram multilingual transcription]
    DEEPGRAM --> DG_OK{Transcript produced?}
    DG_OK -- yes --> SAVE
    DG_OK -- no --> UNAVAILABLE[Mark transcript unavailable]
    SAVE --> RAG_READY[Ready for chunking and RAG]
    UNAVAILABLE --> RAG_LIMITED[Metadata-only limited evidence]
```

Transcript completeness is checked against known duration. A short partial transcript is not accepted as final when a better fallback can be attempted.

## Evidence Index Design

CreatorLens AI does not send raw pages directly to the LLM. It builds a retrieval-ready evidence index.

| Source type | Built from | Why it matters |
| --- | --- | --- |
| `metadata` | creator, views, likes, comments, duration, upload date, transcript source, missing fields | Answers factual metric questions without hallucination |
| `description` | YouTube descriptions, Instagram/Facebook captions | Captures creator framing and CTA language |
| `hook` | first timed transcript segments or first caption sentence | Supports first-5-seconds hook comparison |
| `transcript` | transcript segments grouped into chunks | Supports deeper RAG reasoning and citations |

Each chunk stores:

| Payload field | Purpose |
| --- | --- |
| `project_id` | Multi-project isolation |
| `slot` | `content_1` or `content_2` |
| `platform` | YouTube, Instagram, or Facebook |
| `source_type` | metadata, description, hook, transcript |
| `start_time`, `end_time` | Timed citations when available |
| `title`, `creator` | Better citation context |
| `text` | Evidence content |
| `content_hash` | Stable dedupe/debug identity |
| `citation_label` | Human-readable citation in chat |

## RAG Chat Architecture

```mermaid
flowchart TD
    QUESTION[User question] --> ROUTER[Query Router]
    ROUTER --> INTENT{Intent}
    INTENT --> METRIC[Direct metric answer]
    INTENT --> COMPARE[Comparative reasoning]
    INTENT --> HOOK[Hook / transcript question]
    INTENT --> GENERAL[General creator strategy]

    COMPARE --> BALANCED[Balanced retrieval from Content 1 and Content 2]
    HOOK --> FILTERED[Retrieve hook + transcript chunks]
    GENERAL --> RETRIEVE[Retrieve relevant chunks]

    METRIC --> STRUCTURED[Structured metadata context]
    BALANCED --> CONTEXT[Context Builder]
    FILTERED --> CONTEXT
    RETRIEVE --> CONTEXT
    STRUCTURED --> CONTEXT

    CONTEXT --> PROMPT[Senior creator strategist prompt]
    PROMPT --> LLM[Gemini Flash via LangChain]
    LLM --> STREAM[Stream tokens]
    STREAM --> CITE[Attach backend citations]
```

The chat supports questions such as:

- What is the engagement rate of each content item?
- Compare the hooks in the first 5 seconds.
- Why did Content 1 get more engagement than Content 2?
- Who is the creator of Content 2 and what public follower/subscriber count is available?
- Suggest 3 improvements for Content 2 based on what worked in Content 1.

For comparative reasoning, retrieval is balanced across both content items so the answer does not overfit to whichever chunk ranked first.

## Creator Insight Summary

The Creator Insight Summary is deterministic. It does not call the LLM, and it does not claim to predict virality. It produces fast, explainable creator review signals from extracted evidence.

| Signal | Meaning | Inputs |
| --- | --- | --- |
| Public performance score | How strongly the content performed using confirmed metrics | views, interactions, engagement rate |
| Creator efficiency score | How much the content overperformed relative to creator size | views/subscribers, interactions/subscribers |
| Creative structure score | How clear the content structure appears | hook, caption, CTA, audience specificity, problem-solution framing |
| Evidence confidence | How much confirmed evidence is available | metadata completeness and metric availability |

Overall Creator Insight Score combines:

```text
35% public performance
30% creator-size efficiency
25% creative structure
10% metric confidence
```

This separation is intentional. Metadata availability is useful for confidence, but it is not treated as a creative strength. A smaller creator with far more views and likes can correctly win on creator efficiency even if another content item has a more explicit hook.

## Data Integrity Rules

CreatorLens AI follows strict evidence rules:

- Missing views, likes, comments, duration, follower counts, and transcript evidence are not estimated.
- Unavailable fields stay unavailable in the UI and RAG context.
- LLM responses are instructed not to invent metrics.
- Metadata availability supports confidence only; it is not a performance score.
- Scores are heuristic review signals, not guaranteed performance predictions.
- Citations are generated from backend evidence chunks, not from frontend decoration.

## Backend Modules

| Area | Files |
| --- | --- |
| API routes | `backend/app/api/projects.py`, `ingestion.py`, `chat.py`, `insights.py`, `metrics.py`, `health.py` |
| Extraction | `backend/app/extractors/youtube_extractor.py`, `instagram_extractor.py`, `facebook_extractor.py` |
| Transcript fallbacks | `backend/app/services/apify_transcript_service.py`, `transcription_service.py` |
| RAG | `backend/app/rag/chunk_builder.py`, `indexing_service.py`, `retrieval_service.py`, `context_builder.py`, `query_router.py`, `chat_service.py` |
| Insight scoring | `backend/app/insights/insight_service.py`, `score_service.py`, `hook_analyzer.py` |
| Persistence | `backend/app/db/models/`, `backend/app/db/repositories/`, Alembic migrations |
| Background workers | `backend/app/workers/celery_app.py`, `ingestion_tasks.py`, `indexing_tasks.py` |
| Config | `backend/app/core/config.py`, `paths.py` |

## Frontend Modules

| Area | Files |
| --- | --- |
| App routes | `frontend/src/app/page.tsx`, `analyze/page.tsx`, `chat/page.tsx` |
| Main workflow | `frontend/src/components/ComparisonWorkspace.tsx` |
| Background progress | `frontend/src/components/IngestionProgressPanel.tsx` |
| Chat | `frontend/src/components/CreatorChatPanel.tsx`, `CreatorChatPage.tsx` |
| Insights | `CreatorInsightSummaryPanel.tsx`, `InsightScoreCard.tsx`, `HookComparisonCard.tsx` |
| Evidence tools | `RagIndexPanel.tsx`, `RetrievalTestPanel.tsx`, `TranscriptPreviewPanel.tsx` |
| API client | `frontend/src/lib/api.ts` |
| Types | `frontend/src/types/project.ts` |

Browser state remains lightweight: the active project ID is stored in local storage so analysis polling can recover after a refresh, while chat session IDs and drafts remain in module memory. The `/chat` page uses the active project and does not currently consume a `projectId` query parameter. Chat trace SSE events are parsed by the API client but are not displayed, and restored chat history currently reloads message text without stored citations.

## API Surface

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Backend health |
| `GET /health/qdrant` | Vector DB configuration/connectivity |
| `GET /health/embeddings` | Embedding model readiness |
| `GET /health/llm` | LLM config check without generation |
| `POST /health/llm/test` | Real LLM generation test |
| `POST /health/llm/stream-test` | Stream a small LLM connectivity test over SSE |
| `POST /api/projects` | Create comparison project |
| `GET /api/projects` | List recent projects |
| `POST /api/projects/{project_id}/ingest` | Queue the complete background ingestion pipeline |
| `GET /api/projects/{project_id}/status` | Poll persisted ingestion progress and failures |
| `POST /api/projects/{project_id}/extract` | Extract metadata and transcripts |
| `GET /api/projects/{project_id}` | Load project detail |
| `GET /api/projects/{project_id}/transcripts` | Transcript preview |
| `GET /api/projects/{project_id}/metadata-availability` | Availability report |
| `GET /api/projects/{project_id}/chunks` | List stored evidence chunks |
| `POST /api/projects/{project_id}/chunks/build` | Build local evidence chunks |
| `POST /api/projects/{project_id}/index` | Embed and index chunks in Qdrant |
| `POST /api/projects/{project_id}/retrieve` | Inspect retrieval results |
| `GET /api/projects/{project_id}/metrics/sources` | Load public and manually verified metric sources |
| `POST /api/projects/{project_id}/metrics/verify` | Save manually verified public metrics |
| `DELETE /api/projects/{project_id}/metrics/sources/{record_id}` | Delete a manually verified metric-source record |
| `GET /api/projects/{project_id}/insights/summary` | Deterministic creator insight summary |
| `POST /api/projects/{project_id}/chat/sessions` | Create or reuse a chat session |
| `GET /api/projects/{project_id}/chat/sessions/{session_id}` | Load stored chat messages |
| `DELETE /api/projects/{project_id}/chat/sessions/{session_id}` | Delete a chat session |
| `POST /api/projects/{project_id}/chat/context-preview` | Inspect the RAG context for a question |
| `POST /api/projects/{project_id}/chat/stream` | Streaming RAG chat |

## Local Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Local URLs:

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| Analyze | http://localhost:3000/analyze |
| Chat | http://localhost:3000/chat |
| Backend health | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |

## Environment Variables

### Backend

| Variable | Required | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | yes | `local` or `production` |
| `SERVICE_ROLE` | deployment | `web` (default) for Render or `worker` for the Azure Celery container |
| `CORS_ORIGINS` | yes | Allowed frontend origins |
| `DATABASE_URL` | yes | PostgreSQL connection for application and Alembic migrations |
| `TEST_DATABASE_URL` | local tests only | Isolated PostgreSQL connection selected with `alembic -x database=test` |
| `DB_POOL_SIZE` | optional | SQLAlchemy persistent connection-pool size; defaults to `5` |
| `DB_MAX_OVERFLOW` | optional | Additional temporary SQLAlchemy connections; defaults to `5` |
| `DB_POOL_RECYCLE_SECONDS` | optional | Recycles pooled connections; defaults to `300` seconds |
| `DB_CONNECT_TIMEOUT_SECONDS` | optional | Bounds PostgreSQL connection attempts; defaults to `10` seconds |
| `REDIS_URL` | Phase 2 deployment | TLS Redis URL used by default for both the Celery broker and result backend |
| `CELERY_BROKER_URL` | optional | Overrides `REDIS_URL` for the Celery broker |
| `CELERY_RESULT_BACKEND` | optional | Overrides `REDIS_URL` for temporary Celery task results |
| `CELERY_RESULT_EXPIRES_SECONDS` | optional | Removes temporary Celery results after `3600` seconds by default |
| `CELERY_VISIBILITY_TIMEOUT_SECONDS` | optional | Broker redelivery window for long tasks; defaults to `3600` seconds |
| `CELERY_MAX_RETRIES` | optional | Maximum background-task retries; defaults to `2` |
| `CELERY_RETRY_BACKOFF_SECONDS` | optional | Initial exponential retry delay; defaults to `15` seconds |
| `CELERY_BROKER_CONNECTION_TIMEOUT_SECONDS` | optional | Bounds queue connection attempts; defaults to `5` seconds |
| `CELERY_WORKER_CONCURRENCY` | optional | Worker process count; keep `1` for the Azure student deployment |
| `CELERY_LOG_LEVEL` | optional | Celery worker log level; defaults to `INFO` |
| `GEMINI_API_KEY` | yes | Gemini chat and reasoning |
| `LLM_PROVIDER` | yes | `gemini` |
| `LLM_MODEL` | yes | Primary Gemini model |
| `LLM_FALLBACK_MODEL` | optional | Fallback Gemini model |
| `LLM_TEMPERATURE` | yes | Default Gemini sampling temperature |
| `LLM_MAX_OUTPUT_TOKENS` | yes | Default generation output limit |
| `DEBUG_RAG_PROMPT` | optional | Prints non-secret RAG context-size diagnostics when enabled |
| `GROQ_API_KEY` | unused/reserved | Present in settings but not used by the current Gemini-only LLM service |
| `QDRANT_URL` | yes | Qdrant Cloud endpoint |
| `QDRANT_API_KEY` | yes | Qdrant API key |
| `QDRANT_COLLECTION` | yes | Vector collection name |
| `EMBEDDING_MODEL_NAME` | yes | FastEmbed model name |
| `YOUTUBE_API_KEY` | recommended | YouTube Data API metadata |
| `APIFY_API_TOKEN` | recommended | YouTube transcript fallback |
| `APIFY_YOUTUBE_TRANSCRIPT_ACTOR` | recommended | Configurable Apify transcript actor |
| `APIFY_YOUTUBE_TRANSCRIPT_INPUT_STYLE` | recommended | Input shape expected by the configured Apify actor |
| `APIFY_YOUTUBE_TRANSCRIPT_TIMEOUT_SECONDS` | recommended | Apify transcript request timeout |
| `DEEPGRAM_API_KEY` | recommended | Audio transcription fallback |
| `TRANSCRIPT_LANGUAGE` | yes | `multi` for language detection |
| `TRANSCRIPT_FALLBACK_LANGUAGES` | yes | Caption language priority |
| `DEEPGRAM_MODEL` | yes | Deepgram transcription model |
| `DEEPGRAM_DETECT_LANGUAGE` | yes | Enables automatic language detection |
| `ASSEMBLYAI_API_KEY` | unused/reserved | Present in settings but not used by the current transcription path |

### Frontend

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | yes | Public backend API base URL |

## Deployment

```mermaid
flowchart LR
    GH[GitHub Repo] --> VERCEL[Vercel Frontend]
    GH --> RENDER[Render Docker Backend]
    RENDER --> QDRANT[Qdrant Cloud]
    RENDER --> GEMINI[Gemini API]
    RENDER --> APIFY[Apify]
    RENDER --> DEEPGRAM[Deepgram]
    VERCEL --> RENDER
    MONITOR[Optional external health monitor] --> RENDER
```

| Component | Platform | Notes |
| --- | --- | --- |
| Frontend | Vercel | Root directory: `frontend` |
| Backend | Render | Docker build from `backend/Dockerfile` |
| Keep-alive monitor | Optional external service | Not configured or verifiable from repository files |
| Vector DB | Qdrant Cloud | Stores evidence chunks and payload metadata |
| LLM | Gemini API | Streaming RAG responses |
| Transcript fallback | Apify + Deepgram | Used only when cheaper/free paths are insufficient |

Render production reminders:

```text
ENVIRONMENT=production
CORS_ORIGINS=https://creator-lens-ai.vercel.app,http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=https://creatorlens-ai.onrender.com
```

Optional external health monitor:

| Setting | Value |
| --- | --- |
| Monitor type | HTTP(s) |
| URL | `https://creatorlens-ai.onrender.com/health` |
| Expected method/result | `GET` request returning HTTP `200` with `{"status":"ok"}` |
| Interval | 5 minutes |
| Purpose | Check public availability; free-tier behavior and monitoring policy remain platform/user controlled |

If a monitor reports `405`, verify it uses the full HTTPS URL above and targets `/health`, not a POST-only API route. The backend health endpoint is intentionally cheap and does not call Gemini, Qdrant, Apify, or Deepgram.

## Cost and Scale Strategy

The lowest-cost architecture is to avoid unnecessary LLM and paid transcription calls.

| Cost driver | Current strategy | Production upgrade |
| --- | --- | --- |
| Embeddings | FastEmbed local BGE model, no embedding API cost | Batch embedding workers |
| LLM calls | Only chat/reasoning uses Gemini | Cache common questions and summaries |
| Transcript extraction | Free captions first, Apify/Deepgram only as fallback | URL-level transcript cache and retry queue |
| Vector storage | Qdrant payload filters per project/slot | Payload indexes, collection sharding if needed |
| Database | PostgreSQL on isolated Neon branches | Add caching, background jobs, and production-scale operational controls |
| Backend work | Celery jobs through Upstash Redis with persisted status | Add queue-depth autoscaling and workload-specific worker pools |
| Cold starts | Optional external health monitoring for the Render demo | Paid always-on instance or autoscaled worker/API split |

For 1000 creators/day:

- Cache metadata, transcripts, chunks, and embeddings by normalized URL and content hash.
- Do not re-embed unchanged content.
- Use background jobs for extraction and indexing.
- Keep deterministic metric and scoring logic outside the LLM.
- Use paid transcript fallback only when direct captions are blocked or incomplete.
- Add observability around extraction failures, transcript coverage, Qdrant indexing, and LLM latency.
- If desired, use an external health monitor for demo availability while recognizing that free-tier hosting is not a paid production SLA.

## Quality Trade-Offs

| Decision | Why |
| --- | --- |
| FastEmbed BGE instead of paid embeddings | Lower recurring cost and strong retrieval quality for short evidence chunks |
| Qdrant instead of local-only vector DB | Production-style vector service with payload filtering |
| Gemini Flash instead of heavier model by default | Good reasoning/cost balance for streamed creator chat |
| Deterministic insight scoring | Fast, explainable, and does not hallucinate metrics |
| Layered transcript fallback | Social transcript extraction is unreliable from cloud IPs |
| PostgreSQL with Alembic | Durable deployed state and reviewable schema evolution; SQLite is fallback-only during migration |

## Validation Commands

```powershell
cd backend
python -m compileall app
```

```powershell
cd frontend
npm run build
```

Health checks:

```text
GET /health
GET /health/qdrant
GET /health/embeddings
GET /health/llm
POST /health/llm/test
```

## Demo Script Summary

1. Open the live frontend.
2. Paste Content 1 and Content 2 URLs.
3. Run analysis.
4. Verify metadata, engagement rate, missing fields, transcript source, and transcript segment count.
5. Watch background ingestion reach `READY` or `PARTIAL_READY` and verify evidence is indexed.
6. Show Creator Insight Summary.
7. Ask the RAG chat:
   - What is the engagement rate of each content item?
   - Compare the hooks in the first 5 seconds.
   - Why did Content 1 get more engagement than Content 2?
   - Suggest 3 improvements for Content 2 based on what worked in Content 1.
8. Point out streaming, citations, memory, and evidence limitations.


## Engineering Principle

CreatorLens AI is designed around one rule: do not pretend unavailable evidence exists. The system can be creative in its recommendations, but the factual base must come from confirmed public metadata, transcript chunks, and cited retrieval evidence.

## 🔒 License & Usage

Copyright © 2026 Dilojan Ravindrarasa. All Rights Reserved.

CreatorLens AI is publicly available primarily for **portfolio review, technical evaluation, educational inspection, and demonstration purposes**.

This project is **not released under an open-source license**. No permission is granted to reproduce or redistribute substantial portions of the source code, create derivative products based substantially on it, or use it commercially without prior written permission from the copyright holder.

Public availability of this repository does not waive the author's copyright or grant unrestricted reuse rights.

For complete terms, see the [`LICENSE`](./LICENSE) file.
