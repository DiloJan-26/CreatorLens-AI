# CreatorLens AI

## Overview

CreatorLens AI is a full-stack creator intelligence application for comparing any two supported short-form content URLs with cited, retrieval-grounded insights.

The app accepts Content URL 1 and Content URL 2, auto-detects each platform, extracts public metadata and transcript evidence when available, builds a vector search index, and streams cited Creator Chat answers with memory.

## Supported Comparisons

- YouTube vs YouTube
- YouTube vs Instagram
- YouTube vs Facebook
- Instagram vs Instagram
- Instagram vs Facebook
- Facebook vs Facebook

Supported URL types:

- YouTube Shorts and public YouTube watch URLs
- Instagram Reels, posts, and TV URLs
- Facebook Reels, public watch URLs, and public post video URLs

## Current Capabilities

- FastAPI backend
- Next.js frontend
- Content URL 1 and Content URL 2 project creation
- Platform auto-detection for YouTube, Instagram, and Facebook
- SQLite project, content, transcript, chunk, metric, and chat memory storage
- YouTube public metadata extraction with yt-dlp
- YouTube transcript extraction with youtube-transcript-api
- Instagram public metadata extraction with yt-dlp
- Instagram transcription using Deepgram when a public audio URL is available
- Facebook best-effort public metadata extraction with yt-dlp
- Facebook transcription attempt with Deepgram when public media audio is available
- Normalized metadata for supported platforms
- Metadata Availability summary
- Confirmed Public Metrics display
- FastEmbed embeddings with `BAAI/bge-small-en-v1.5`
- Qdrant Cloud vector storage
- Slot-aware RAG chunks for same-platform comparisons
- Source retrieval with platform, content, and source-type filters
- Gemini 2.5 Flash streaming chat through LangChain
- Memory-aware chat sessions
- Backend-derived citations shown under assistant answers

## Metadata Extraction

The system attempts to extract transcript, views, likes/reactions, comments, creator, follower/subscriber count, hashtags, upload date, and duration. Platform limitations may make some fields unavailable; CreatorLens AI does not estimate missing metrics.

Each content item stores extracted values when available. Missing values are stored as `null`, shown as Unavailable, and included in `missing_fields`.

Facebook public metadata is extracted when available. Missing fields are marked unavailable and are not estimated.

## Transcript Pipeline

- YouTube transcripts come from public captions/subtitles when available.
- Instagram transcripts are generated with Deepgram when yt-dlp exposes a public audio URL.
- Facebook transcripts are generated with Deepgram when public media audio can be extracted.
- If transcript evidence is unavailable, the UI shows Unavailable and keeps metadata extraction results.

## Vector Search Index

The search index is built from each content item:

- Metadata chunks
- Description/caption chunks
- Hook chunks from opening transcript segments
- Transcript chunks

Each chunk payload includes project ID, content slot, platform, source type, timing when available, title, creator, text, content hash, and a citation label such as:

- `Content 1 · YouTube · metadata`
- `Content 2 · YouTube · hook · 0.16s-8.44s`
- `Content 2 · Facebook · transcript · 0.16s-12.40s`

Payload filters support project, content slot, platform, and source type.

## Streaming Creator Chat

Streaming Creator Chat answers questions using structured metadata and retrieved source chunks. The backend prepares citations, streams assistant tokens, stores chat history, and displays sources separately under each answer.

Suggested demo questions:

- What is the engagement rate of each content item?
- Compare the hooks in the first 5 seconds.
- Which content has stronger confirmed public engagement?
- What metadata is missing or unavailable?
- Suggest improvements for Content 2 based on Content 1.

## Confirmed Public Metrics and Missing Data

CreatorLens AI uses Confirmed Public Metrics only.

- Missing views, likes, reactions, comments, shares, follower/subscriber counts, upload dates, duration, and transcript evidence are shown as Unavailable.
- Missing public metrics are not converted to zero.
- Missing public metrics are not estimated by the backend or by Gemini.
- Instagram and Facebook public extraction can be incomplete because platform UIs and public metadata endpoints expose different values.
- Facebook extraction is best-effort and does not use login, cookies, Meta API, or private/authenticated scraping.

## Cost and Scaling Choices

- SQLite keeps local demo state simple.
- FastEmbed keeps embeddings local and cost-free.
- Qdrant Cloud stores citation-ready vectors.
- Retrieval filters keep context small.
- Metadata questions can be answered from SQLite to reduce unnecessary LLM calls.
- Gemini 2.5 Flash is selected for cost-aware streaming reasoning.
- Deepgram is used only when public media audio is available.
- Re-indexing replaces old project vectors by project ID.

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

Local URLs:

- http://localhost:8000/health
- http://localhost:8000/health/qdrant
- http://localhost:8000/health/embeddings
- http://localhost:8000/health/llm
- http://localhost:8000/docs
- http://localhost:8000/api/projects
- http://localhost:3000

Use `.env.example` and `backend/.env.example` as references.

