"use client";

import { useState } from "react";

type BackendStatus =
  | {
      status: "idle";
      message: string;
    }
  | {
      status: "ok";
      message: string;
    }
  | {
      status: "error";
      message: string;
    };

type HealthResponse = {
  status?: string;
  service?: string;
  environment?: string;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>({
    status: "idle",
    message: "Backend status has not been checked yet.",
  });
  const [isChecking, setIsChecking] = useState(false);

  async function checkBackend() {
    setIsChecking(true);
    setBackendStatus({
      status: "idle",
      message: "Checking backend...",
    });

    try {
      const response = await fetch(`${apiBaseUrl}/health`, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Backend returned HTTP ${response.status}`);
      }

      const data = (await response.json()) as HealthResponse;

      if (data.status === "ok" && data.service) {
        setBackendStatus({
          status: "ok",
          message: `${data.status} - ${data.service}`,
        });
        return;
      }

      setBackendStatus({
        status: "error",
        message: "Backend responded, but the health payload was unexpected.",
      });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not reach the backend.";

      setBackendStatus({
        status: "error",
        message,
      });
    } finally {
      setIsChecking(false);
    }
  }

  return (
    <main className="min-h-screen bg-stone-50 text-slate-950">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-10 sm:px-8 lg:px-10">
        <header className="mb-10 flex items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <p className="text-lg font-semibold">CreatorLens AI</p>
        </header>

        <div className="grid flex-1 items-center gap-10 lg:grid-cols-[1fr_420px]">
          <div className="max-w-3xl">
            <h1 className="text-4xl font-semibold leading-tight text-slate-950 sm:text-5xl">
              Compare Shorts and Reels with cited creator intelligence.
            </h1>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={checkBackend}
                disabled={isChecking}
                className="inline-flex h-11 items-center justify-center rounded-md bg-slate-950 px-5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              >
                {isChecking ? "Checking..." : "Check Backend"}
              </button>
              <button
                type="button"
                disabled
                className="inline-flex h-11 items-center justify-center rounded-md border border-slate-300 px-5 text-sm font-medium text-slate-400"
              >
                Analyze Videos - Coming Soon
              </button>
            </div>

            <div
              className={`mt-5 rounded-md border px-4 py-3 text-sm ${
                backendStatus.status === "ok"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : backendStatus.status === "error"
                    ? "border-rose-200 bg-rose-50 text-rose-800"
                    : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              Backend status: {backendStatus.message}
            </div>
          </div>

          <div className="grid gap-4">
            <VideoInputCard
              label="YouTube"
              title="Input YouTube Short URL"
              placeholder="https://youtube.com/shorts/..."
            />
            <VideoInputCard
              label="Instagram"
              title="Input Instagram Reel URL"
              placeholder="https://www.instagram.com/reel/..."
            />
            
          </div>
        </div>
      </section>
    </main>
  );
}

function VideoInputCard({
  label,
  title,
  placeholder,
}: {
  label: string;
  title: string;
  placeholder: string;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
        {label}
      </p>
      <label className="mt-3 block text-sm font-medium text-slate-900">
        {title}
        <input
          type="url"
          placeholder={placeholder}
          className="mt-3 h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
        />
      </label>
    </section>
  );
}
