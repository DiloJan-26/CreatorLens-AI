# CreatorLens AI

CreatorLens AI is a full-stack RAG chatbot planned for comparing one YouTube Short and one Instagram Reel. It will extract transcript and metadata signals, normalize them, retrieve relevant evidence, and answer comparison questions through a streaming chat interface.

## Planned Features

- Submit one YouTube Short URL and one Instagram Reel URL
- Extract transcripts, captions, metadata, and engagement signals
- Normalize platform-specific metadata into a shared schema
- Chunk transcript and metadata evidence
- Store embeddings in Qdrant
- Use RAG for grounded comparison answers
- Stream chatbot responses to the frontend
- Avoid LLM calls for simple structured metadata questions where possible

## Tech Stack Plan

- Frontend: Next.js
- Backend: FastAPI
- Vector database: Qdrant Cloud
- RAG orchestration: LangChain later, after the lightweight foundation
- LLM providers: Gemini and/or Groq
- Extraction services: YouTube transcript tooling, yt-dlp, Apify, Deepgram as needed

## Local Backend Setup

From `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
