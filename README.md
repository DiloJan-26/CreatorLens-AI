# CreatorLens AI

## Overview

CreatorLens AI is a full-stack creator intelligence application for comparing any two supported short-form content URLs with cited, retrieval-grounded insights.

The app accepts Content URL 1 and Content URL 2, auto-detects each platform, extracts public metadata and transcript evidence when available, builds a vector search index, generates a Creator Insight Summary, and streams cited Creator Chat answers with memory.

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
- Multilingual Transcript Support for English, Hindi, Tamil, and supported multilingual audio
- Instagram transcription using Deepgram multilingual transcription when a public audio URL is available
- Facebook best-effort public metadata extraction with yt-dlp
- Facebook transcription attempt with Deepgram multilingual transcription when public media audio is available
- Normalized metadata for supported platforms
- Metadata Availability summary
- Confirmed public metrics display
- FastEmbed embeddings with `BAAI/bge-small-en-v1.5`
- Qdrant Cloud vector storage
- Slot-aware RAG chunks for same-platform comparisons
- Source retrieval with platform, content, and source-type filters
- Gemini 2.5 Flash streaming chat through LangChain
- Memory-aware chat sessions
- Backend-derived citations shown under assistant answers
- Creator Insight Summary with Hook Analysis, heuristic creator insight score, Metadata Confidence, strengths, weaknesses, recommendations, and Example Rewrite
- Creator Insight Summary context integrated into streaming Creator Chat

## Creator Insight Summary

The Creator Insight Summary turns extracted evidence into structured creator intelligence without adding another LLM scoring step.

It includes:

- Overall comparison for Content 1 and Content 2
- Content 1 insight card
- Content 2 insight card
- Hook Analysis
- Heuristic creator insight score
- Metadata Confidence note
- Strengths and weaknesses
- Missing metadata
- Recommendations
- Example Rewrite when enough context is available

Scores are heuristic signals designed to support creator review. They are not a certainty about future performance.

## Hook Analysis

Hook Analysis uses rule-based classification over transcript openings when available. If transcript evidence is unavailable, it falls back to the caption or description opening.

Hook labels include patterns such as:

- problem_solution
- curiosity
- founder_story
- statistic
- question
- transformation
- product_reveal
- educational
- lifestyle
- trend_based
- weak_context_only
- unavailable

Hook scores use simple deterministic signals such as specificity, payoff clarity, curiosity gap, concise opening, and audience relevance.

## Heuristic Insight Scores

The heuristic creator insight score combines:

- hook clarity
- problem-solution clarity
- CTA strength
- caption strength
- audience specificity
- Metadata Availability
- engagement confidence from confirmed public metrics

Missing fields are unavailable, not estimated. The scoring service does not invent views, likes, reactions, comments, shares, follower/subscriber counts, upload dates, duration, or transcript evidence.

## Streaming Creator Chat

Streaming Creator Chat answers questions using:

- Creator Insight Summary
- structured metadata
- confirmed public metrics
- retrieved source chunks
- recent chat memory

The backend prepares citations, streams assistant tokens, stores chat history, and displays sources separately under each answer. Deterministic direct answers handle high-risk factual questions when possible, such as missing metadata, engagement rates, hook type, Creator Insight Score, and comparison winners.

## Metadata Availability and Missing Fields

CreatorLens AI uses confirmed public metrics only.

- Missing views, likes, reactions, comments, shares, follower/subscriber counts, upload dates, duration, and transcript evidence are shown as Unavailable.
- Missing public metrics are not converted to zero.
- Missing public metrics are not estimated by the backend or by Gemini.
- Instagram and Facebook public extraction can be incomplete because platform UIs and public metadata endpoints expose different values.
- Facebook extraction is best-effort and does not use login, cookies, Meta API, or private/authenticated scraping.

## Transcript Pipeline

- YouTube transcripts prefer public captions/subtitles when available.
- Caption/subtitle language fallback prioritizes English (`en`), Hindi (`hi`), and Tamil (`ta`), then falls back to any available caption language.
- Instagram transcripts are generated with Deepgram multilingual transcription when yt-dlp exposes a public audio URL.
- Facebook transcripts are generated with Deepgram multilingual transcription when public media audio can be extracted.
- If transcript evidence is unavailable, the UI shows Unavailable and keeps metadata extraction results.
- Transcript Language, detected language, source, and source notes are stored when available.

## Multilingual Transcript Support

CreatorLens AI uses best-effort transcription for English, Hindi, Tamil, and supported multilingual audio.

- Captions/subtitles are preferred when available.
- Deepgram multilingual transcription is used when public media audio is available.
- Missing transcripts are marked unavailable, not fabricated.
- Transcript Language is shown in transcript previews and content cards when known.
- Mixed-language, noisy, unsupported, or non-public media can still fail; those cases are shown as Transcript unavailable.

## Vector Search Index

The search index is built from each content item:

- Metadata chunks
- Description/caption chunks
- Hook chunks from opening transcript segments
- Transcript chunks

Each chunk payload includes project ID, content slot, platform, source type, timing when available, title, creator, text, content hash, and a citation label such as:

- `Content 1 - YouTube - metadata`
- `Content 2 - YouTube - hook - 0.16s-8.44s`
- `Content 2 - Facebook - transcript - 0.16s-12.40s`

Payload filters support project, content slot, platform, and source type.

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
- http://localhost:8000/api/projects/{project_id}/insights/summary
- http://localhost:3000

Use `.env.example` and `backend/.env.example` as references.