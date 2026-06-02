# CreatorLens AI

CreatorLens AI is a full-stack application for comparing a YouTube Short and an Instagram Reel. It extracts public creator/video signals, normalizes them into a shared schema, stores local project state, and is being built toward cited RAG chat.

## Current Status

Implemented:

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
- Instagram transcription using Deepgram when an audio URL is available
- Normalized video metadata
- SQLite storage for both YouTube and Instagram metadata
- SQLite storage for both YouTube and Instagram transcript segments
- Frontend dynamic YouTube card
- Frontend dynamic Instagram card
- Honest unavailable states for missing public metrics
- Qdrant Cloud-ready health check

Not implemented yet:

- Apify fallback/enrichment
- AssemblyAI fallback
- Transcript chunking for RAG
- Embeddings
- Qdrant chunk storage
- LangChain RAG
- Streaming chat
- Memory

## Tech Stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Pydantic, SQLite
- YouTube extraction: yt-dlp, youtube-transcript-api
- Instagram extraction: yt-dlp
- Instagram transcription: Deepgram
- Planned vector database: Qdrant Cloud
- Planned RAG orchestration: LangChain

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
- http://localhost:8000/docs
- http://localhost:8000/api/projects
- http://localhost:3000

## Environment Variables

Use `.env.example` and `backend/.env.example` as references.
