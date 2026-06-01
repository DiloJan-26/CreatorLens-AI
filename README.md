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
- Normalized video metadata
- Frontend dynamic YouTube card
- Instagram-ready schema with pending UI
- Qdrant Cloud-ready health check

Not implemented yet:

- Instagram extraction
- Embeddings
- Qdrant chunk storage
- LangChain RAG
- Streaming chat
- Memory

## Tech Stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Pydantic, SQLite
- YouTube extraction: yt-dlp, youtube-transcript-api
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

