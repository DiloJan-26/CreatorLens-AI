# CreatorLens AI

CreatorLens AI is a full-stack application for comparing a YouTube Short and an Instagram Reel. The goal is to extract metadata and transcript evidence, calculate engagement signals, store searchable context, and support a cited chat experience for creator analysis.

## Current Status

Implemented so far:

- FastAPI backend
- Next.js frontend
- Backend health check
- Qdrant Cloud-ready health check
- Project creation API
- URL validation for YouTube and Instagram
- SQLite local project storage
- Frontend project creation flow

## Planned Next Features

- YouTube metadata and transcript extraction
- Instagram metadata and transcript extraction
- Engagement-rate calculation
- Transcript chunking
- Embeddings
- Qdrant storage
- LangChain RAG
- Streaming cited chat
- Memory

## Tech Stack

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI, Pydantic, SQLite
- Vector database: Qdrant Cloud
- Planned RAG orchestration: LangChain
- Planned model providers: Gemini and/or Groq

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
