# CreatorLens AI

CreatorLens AI is a full-stack creator intelligence product for comparing any two supported short-form content URLs with confirmed public metadata, multilingual transcript evidence, cited insights, and streaming AI chat.

Users paste Content URL 1 and Content URL 2, click **Analyze Content**, and CreatorLens AI runs the normal workflow automatically:

```text
URLs -> platform detection -> public extraction -> transcripts -> evidence index -> Creator Insight Summary -> cited chat
```

No signup is required for the local demo.

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

## Key Features

- Universal Content URL 1 and Content URL 2 comparison
- Platform auto-detection for YouTube, Instagram, and Facebook
- Best-effort public metadata extraction
- Multilingual transcript support
- Metadata Availability with unavailable fields clearly marked
- Confirmed public metrics only; missing values are not estimated
- Rule-based Hook Analysis
- Heuristic Creator Insight Score
- Creator Insight Summary with strengths, weaknesses, recommendations, and Example Rewrite
- FastEmbed embeddings with `BAAI/bge-small-en-v1.5`
- Qdrant vector storage for cited evidence
- Streaming Creator Chat using Gemini 2.5 Flash through LangChain
- Backend-derived citations and memory-aware chat sessions
- Dedicated chat page with project context
- Dark/light theme toggle persisted as `creatorlens_theme`
- No signup, authentication, payment, or account setup required for the demo

## Metadata Availability

CreatorLens AI separates confirmed public metrics from unavailable fields.

Checked fields include:

- transcript
- views
- likes/reactions
- comments
- creator
- follower/subscriber count
- hashtags
- upload date
- duration

Missing fields remain **Unavailable**. They are not converted to zero, estimated by the backend, or filled in by Gemini.

## Multilingual Transcripts

Transcript extraction is best-effort:

- YouTube captions/subtitles are preferred.
- Language fallback prioritizes English (`en`), Hindi (`hi`), and Tamil (`ta`), then other available caption languages.
- Instagram and Facebook transcription use Deepgram multilingual transcription when public audio is available.
- Transcript Language, detected language, transcript source, and transcript source notes are stored when available.
- Mixed-language, noisy, unsupported, or non-public media can still fail; those cases are shown as Transcript unavailable.

## Evidence Index

The evidence index is built automatically after analysis. It creates retrieval-ready chunks from:

- metadata
- descriptions/captions
- hook openings
- transcript segments

Chunk payloads include project ID, content slot, platform, source type, timing when available, title, creator, text, content hash, and citation labels such as:

- `Content 1 - YouTube - metadata`
- `Content 2 - Instagram - hook - 0.00s-5.00s`
- `Content 2 - Facebook - transcript - 0.16s-12.40s`

The advanced **Evidence Explorer** lets interviewers or power users inspect retrieved transcript, caption, metadata, and hook chunks.

## Creator Insight Summary

The Creator Insight Summary turns extracted evidence into structured creator intelligence without an extra LLM scoring call.

It includes:

- Executive comparison
- Content 1 and Content 2 insight cards
- Hook Analysis
- heuristic Creator Insight Score
- Metadata Confidence note
- strengths and weaknesses
- missing metadata
- recommendations
- Example Rewrite when enough context is available

Scores are heuristic review signals, not guaranteed performance predictions.


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
- http://localhost:3000/analyze
- http://localhost:3000/chat

Use `.env.example` and `backend/.env.example` as references.
