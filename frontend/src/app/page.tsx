"use client";

import { useState } from "react";

import { ProjectStatusCard } from "@/components/ProjectStatusCard";
import { SystemStatusCard } from "@/components/SystemStatusCard";
import { VideoUrlForm } from "@/components/VideoUrlForm";
import { checkBackend, createProject } from "@/lib/api";
import type { ProjectCreateResponse } from "@/types/project";

export default function Home() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [backendStatus, setBackendStatus] = useState(
    "Backend status has not been checked yet.",
  );
  const [isChecking, setIsChecking] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [project, setProject] = useState<ProjectCreateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleBackendCheck() {
    setIsChecking(true);
    setBackendStatus("Checking backend...");

    try {
      const health = await checkBackend();

      if (health.status === "ok" && health.service) {
        setBackendStatus(`${health.status} - ${health.service}`);
        return;
      }

      setBackendStatus(health.message ?? "Backend responded unexpectedly.");
    } catch (caughtError) {
      setBackendStatus(getErrorMessage(caughtError));
    } finally {
      setIsChecking(false);
    }
  }

  async function handleCreateProject() {
    setIsSubmitting(true);
    setProject(null);
    setError(null);

    try {
      const createdProject = await createProject({
        youtube_url: youtubeUrl,
        instagram_url: instagramUrl,
      });

      setProject(createdProject);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen bg-stone-50 text-slate-950">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-10 sm:px-8 lg:px-10">
        <header className="mb-10 flex items-center justify-between gap-4 border-b border-slate-200 pb-5">
          <p className="text-lg font-semibold">CreatorLens AI</p>
        </header>

        <div className="grid flex-1 items-center gap-10 lg:grid-cols-[1fr_440px]">
          <section className="max-w-3xl">
            <h1 className="text-4xl font-semibold leading-tight text-slate-950 sm:text-5xl">
              Compare Shorts and Reels with cited creator intelligence.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
              project creation flow, URL validation, SQLite
              project storage, and frontend-backend integration.
            </p>

            <div className="mt-8 grid gap-4">
              <SystemStatusCard
                statusText={backendStatus}
                isChecking={isChecking}
                onCheck={handleBackendCheck}
              />
              <ProjectStatusCard project={project} error={error} />
            </div>
          </section>

          <VideoUrlForm
            youtubeUrl={youtubeUrl}
            instagramUrl={instagramUrl}
            setYoutubeUrl={setYoutubeUrl}
            setInstagramUrl={setInstagramUrl}
            onSubmit={handleCreateProject}
            isSubmitting={isSubmitting}
          />
        </div>
      </section>
    </main>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}
