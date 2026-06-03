"use client";

import { useState } from "react";

import { ContentCard } from "@/components/ContentCard";
import { CreatorChatPanel } from "@/components/CreatorChatPanel";
import { CreatorInsightSummaryPanel } from "@/components/CreatorInsightSummaryPanel";
import { MetadataAvailabilityPanel } from "@/components/MetadataAvailabilityPanel";
import { ProjectStatusCard } from "@/components/ProjectStatusCard";
import { RagIndexPanel } from "@/components/RagIndexPanel";
import { RetrievalTestPanel } from "@/components/RetrievalTestPanel";
import { SystemStatusCard } from "@/components/SystemStatusCard";
import { TranscriptPreviewPanel } from "@/components/TranscriptPreviewPanel";
import { VideoUrlForm } from "@/components/VideoUrlForm";
import { checkBackend, createProject, extractProject } from "@/lib/api";
import type {
  IndexProjectResponse,
  ProjectCreateResponse,
  ProjectDetailResponse,
} from "@/types/project";

export default function Home() {
  const [content1Url, setContent1Url] = useState("");
  const [content2Url, setContent2Url] = useState("");
  const [backendStatus, setBackendStatus] = useState(
    "Backend status has not been checked yet.",
  );
  const [isChecking, setIsChecking] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [createdProject, setCreatedProject] =
    useState<ProjectCreateResponse | null>(null);
  const [projectDetail, setProjectDetail] =
    useState<ProjectDetailResponse | null>(null);
  const [indexResult, setIndexResult] = useState<IndexProjectResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const indexReady = indexResult?.status === "indexed";

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

  async function handleAnalyzeVideos() {
    setIsSubmitting(true);
    setProgressMessage("Creating project...");
    setCreatedProject(null);
    setProjectDetail(null);
    setIndexResult(null);
    setError(null);

    try {
      const created = await createProject({
        content_1_url: content1Url,
        content_2_url: content2Url,
      });

      setCreatedProject(created);
      setProgressMessage("Extracting public metadata and transcripts...");

      const detail = await extractProject(created.project_id);

      setProjectDetail(detail);
      setProgressMessage(
        "Build the Qdrant search index to test cited source retrieval and use Creator Chat.",
      );
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
      setProgressMessage(null);
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

        <div className="grid flex-1 gap-10 lg:grid-cols-[1fr_440px]">
          <section className="max-w-3xl">
            <h1 className="text-4xl font-semibold leading-tight text-slate-950 sm:text-5xl">
              Compare Any Two Shorts/Reels with cited creator intelligence.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
              Analyze YouTube Shorts, Instagram Reels, and Facebook Reels/post
              videos, then retrieve cited creator insights from transcripts,
              captions, descriptions, hashtags, and metadata.
            </p>

            <div className="mt-8 grid gap-4">
              <SystemStatusCard
                statusText={backendStatus}
                isChecking={isChecking}
                onCheck={handleBackendCheck}
              />
              <ProjectStatusCard
                createdProject={createdProject}
                projectDetail={projectDetail}
                progressMessage={progressMessage}
                error={error}
              />
            </div>
          </section>

          <VideoUrlForm
            content1Url={content1Url}
            content2Url={content2Url}
            setContent1Url={setContent1Url}
            setContent2Url={setContent2Url}
            onSubmit={handleAnalyzeVideos}
            isSubmitting={isSubmitting}
          />
        </div>

        <section className="mt-10 grid gap-4 lg:grid-cols-2">
          <ContentCard
            label="Content 1"
            item={contentItem(projectDetail, "content_1")}
            isPending={isSubmitting}
          />
          <ContentCard
            label="Content 2"
            item={contentItem(projectDetail, "content_2")}
            isPending={isSubmitting}
          />
        </section>

        {projectDetail ? (
          <>
            <section className="mt-4 grid gap-4">
              <MetadataAvailabilityPanel projectId={projectDetail.project_id} />
            </section>

            <section className="mt-4 grid gap-4 lg:grid-cols-2">
              <TranscriptPreviewPanel
                projectId={projectDetail.project_id}
                item={contentItem(projectDetail, "content_1")}
                label="Content 1"
              />
              <TranscriptPreviewPanel
                projectId={projectDetail.project_id}
                item={contentItem(projectDetail, "content_2")}
                label="Content 2"
              />
            </section>

            <section className="mt-4 grid gap-4">
              <CreatorInsightSummaryPanel
                projectId={projectDetail.project_id}
                indexReady={indexReady}
              />
            </section>

            <section className="mt-4 grid gap-4">
              <RagIndexPanel
                projectId={projectDetail.project_id}
                onIndexed={setIndexResult}
              />
              <RetrievalTestPanel
                projectId={projectDetail.project_id}
                indexReady={indexReady}
              />
              <CreatorChatPanel
                projectId={projectDetail.project_id}
                indexReady={indexReady}
              />
            </section>
          </>
        ) : null}
      </section>
    </main>
  );
}

function contentItem(
  projectDetail: ProjectDetailResponse | null,
  slot: "content_1" | "content_2",
) {
  return (
    projectDetail?.content_items.find((item) => item.slot === slot) ?? null
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}
