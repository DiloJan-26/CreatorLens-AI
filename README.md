# CreatorLens AI

CreatorLens AI is a full-stack creator intelligence application for comparing a YouTube Short and an Instagram Reel. It extracts public creator/video signals, normalizes them into a shared schema, stores local project state, builds a vector search index, and streams cited creator insights through a memory-aware chat experience.

## Current Capabilities

- FastAPI backend
- Next.js frontend
- Project creation flow
- SQLite project storage
- SQLite video metadata storage
- SQLite transcript segment storage
- SQLite chat session and message storage
- YouTube extraction pipeline
- YouTube metadata extraction with yt-dlp
- YouTube transcript extraction with youtube-transcript-api
- Instagram metadata extraction with yt-dlp
- Instagram transcription using Deepgram when a public audio URL is available
- Normalized YouTube and Instagram metadata
- Description/caption storage for retrieval context
- Metric source notes for YouTube and Instagram
- Transcript source notes for YouTube and Instagram
- Transcript preview endpoint
- Dynamic YouTube and Instagram insight cards
- Honest unavailable states for missing public metrics
- FastEmbed embedding foundation
- Qdrant Cloud vector storage
- SQLite RAG chunk storage
- Metadata, description/caption, hook, and transcript chunks
- Vector indexing endpoint
- Source retrieval endpoint
- LangChain and Gemini LLM configuration foundation
- Safe LLM health endpoint
- Memory-aware chat session endpoints
- Query intent routing for chat context
- Structured metadata and retrieved source context builder
- Backend-derived citation preparation
- Streaming Creator Chat backend endpoint
- Server-sent token, citation, and completion events
- Frontend search index panel
- Frontend source retrieval panel
- Frontend Streaming Creator Chat panel
- Suggested cited insight questions
- Source citation display under assistant answers

## Architecture

CreatorLens AI follows a retrieval-first architecture:

```text
YouTube + Instagram URLs
  -> extraction and normalization
  -> SQLite project/video/transcript storage
  -> chunk builder
  -> rag_chunks table
  -> FastEmbed embeddings
  -> Qdrant vector index
  -> source retrieval
  -> Gemini/LangChain LLM foundation
  -> SQLite chat memory
  -> query routing and grounded context builder
  -> streaming RAG chat backend
  -> frontend Streaming Creator Chat panel
```

## Extraction Pipeline

The backend extracts public metadata and transcript/caption context without guessing missing values.

- YouTube metadata comes from yt-dlp.
- YouTube transcript segments come from youtube-transcript-api when captions are available.
- Instagram metadata comes from yt-dlp.
- Instagram transcripts are generated with Deepgram when a public audio URL is available.
- Missing public metrics are shown as unavailable, not estimated or converted to zero.

## Vector Search Index

The search index is built from multiple evidence types:

- Metadata chunks
- YouTube description chunks
- Instagram caption chunks
- Hook chunks for opening-seconds comparison
- Transcript chunks

Embeddings use FastEmbed with `BAAI/bge-small-en-v1.5`. Vectors are stored in Qdrant Cloud with citation-ready payloads.

## Source Retrieval

The retrieval endpoint searches Qdrant dynamically and returns source chunks with:

- Platform
- Source type
- Score
- Citation label
- Timing when available
- Chunk text

Frontend retrieval filters support platform and source-type narrowing for validating the sources that ground chat answers.

## LLM Configuration

CreatorLens AI includes a lightweight LLM foundation for the Streaming Creator Chat layer.

- Primary provider: Gemini
- Default model: `gemini-2.5-flash`
- Orchestration foundation: LangChain
- Health endpoint: `GET /health/llm`

The LLM client is created lazily and the health endpoint verifies configuration without generating a chat answer. API keys are read from environment variables and are not printed by the application.

## Memory-Aware Chat Storage

The backend stores chat sessions and messages in SQLite so Cited RAG Chat can use recent conversation history. Chat endpoints create, read, clear, and stream memory-aware chat sessions.

## RAG Context Builder

The backend classifies chat questions, selects a retrieval strategy, combines structured YouTube and Instagram metadata with retrieved source chunks, and prepares backend-derived citations.

## Streaming Creator Chat

The frontend Streaming Creator Chat panel calls `POST /api/projects/{project_id}/chat/stream` after extraction and indexing. It streams assistant tokens live, preserves the session ID for follow-up questions, and displays backend-derived sources under assistant answers.

The backend creates or reuses a chat session, saves the user message, builds grounded RAG context, streams Gemini response tokens through LangChain, emits citations as a separate event, and saves the assistant response for memory.

## Data Transparency

CreatorLens AI does not guess missing public metrics.

- YouTube public counts can differ from the live UI because of rounding, caching, timezone differences, and update delay.
- Instagram browser UI may include Facebook-crossposted reactions or comments that public Instagram extraction does not include.
- Missing public metrics are shown as unavailable, not estimated or converted to zero.

## Cost and Scaling Choices

- SQLite keeps local demo state simple.
- FastEmbed avoids paid embedding API cost.
- Qdrant Cloud stores citation-ready vectors.
- Retrieval filters keep context small.
- Re-indexing replaces old project vectors by project ID.
- Gemini 2.5 Flash is selected for low-latency, cost-aware reasoning.
- Metric questions use structured metadata context to reduce unnecessary retrieval and token usage.
- Embeddings stay local with FastEmbed.

## Tech Stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Pydantic, SQLite
- YouTube extraction: yt-dlp, youtube-transcript-api
- Instagram extraction: yt-dlp
- Instagram transcription: Deepgram
- Embeddings: FastEmbed with BAAI/bge-small-en-v1.5
- Vector database: Qdrant Cloud
- RAG orchestration foundation: LangChain
- LLM provider: Gemini 2.5 Flash

## Not Implemented Yet

- Apify fallback/enrichment
- AssemblyAI fallback
- Production deployment
- Analytics and usage monitoring

## Next Step: Final Polish

The next major milestone is final polish, deployment preparation, and a concise README/demo script for recruiters.

## Local Setup

Backend:

```powershell
cd backend
.\.venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm run dev
```

## Local URLs

- http://localhost:8000/health
- http://localhost:8000/health/qdrant
- http://localhost:8000/health/embeddings
- http://localhost:8000/health/llm
- http://localhost:8000/docs
- http://localhost:8000/api/projects
- http://localhost:3000

## Environment Variables

Use `.env.example` and `backend/.env.example` as references.
