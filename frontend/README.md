# CreatorLens AI Frontend

The CreatorLens frontend is a Next.js App Router application for the public V1 comparison, evidence, insights, and streaming chat experience.

## Routes

- `/`: product landing page.
- `/analyze`: creates a two-content project, runs extraction, indexes evidence, and loads deterministic insights.
- `/chat`: opens chat for the active in-memory project.

Active project and chat-session state is stored in browser module memory and is lost on a full refresh. The frontend calls FastAPI directly; there is no Next.js API proxy.

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
