# CreatorLens AI Frontend

The CreatorLens frontend is a Next.js App Router application for the public V1 comparison, evidence, insights, and streaming chat experience.

## Routes

- `/`: product landing page.
- `/analyze`: creates a two-content project, queues background ingestion, polls persisted progress, and loads results when the worker reaches a terminal state.
- `/chat`: opens chat for the active in-memory project.

The active project ID is persisted in browser local storage so `/analyze` can recover the latest ingestion status after a refresh. Chat-session state remains in browser module memory. The frontend calls FastAPI directly; there is no Next.js API proxy.

## Environment

Copy `.env.example` to `.env.local` and set:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

For Vercel, configure `NEXT_PUBLIC_API_BASE_URL` with the public Render backend origin. Do not place backend credentials in frontend environment variables.

## Commands

```powershell
npm install
npm run dev
```

User-executed Phase 0 validation:

```powershell
npm run build
```

The production deployment uses Vercel with `frontend` as the project root.
