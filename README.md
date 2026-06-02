# CreatorLens AI

CreatorLens AI is a full-stack creator intelligence application for comparing a YouTube Short and an Instagram Reel. It extracts public creator/video signals, normalizes them into a shared schema, stores local project state, builds a vector search index, and retrieves cited source chunks for future RAG chat.

## Current Capabilities

- FastAPI backend
- Next.js frontend
- Project creation flow
- SQLite project storage
- SQLite video metadata storage
- SQLite transcript segment storage
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
- Frontend search index panel
- Frontend source retrieval panel

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
  -> upcoming streaming RAG chat
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

Frontend retrieval filters support platform and source-type narrowing before final RAG answer generation is added.

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
- LLM calls are intentionally deferred until the final chat layer.

## Tech Stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Pydantic, SQLite
- YouTube extraction: yt-dlp, youtube-transcript-api
- Instagram extraction: yt-dlp
- Instagram transcription: Deepgram
- Embeddings: FastEmbed with BAAI/bge-small-en-v1.5
- Vector database: Qdrant Cloud
- Planned RAG orchestration: LangChain

## Not Implemented Yet

- Apify fallback/enrichment
- AssemblyAI fallback
- LangChain RAG answer generation
- Streaming chat
- Conversation memory
- Final citations in chatbot answers

## Next Step: Streaming RAG Chat

The next major milestone is a streaming RAG chat layer that uses retrieved YouTube and Instagram chunks as cited evidence.

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
- http://localhost:8000/docs
- http://localhost:8000/api/projects
- http://localhost:3000

## Environment Variables

Use `.env.example` and `backend/.env.example` as references.
