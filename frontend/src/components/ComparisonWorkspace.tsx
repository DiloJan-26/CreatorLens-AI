"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  AnalysisProgress,
  type AnalysisProgressStep,
  type ProgressStatus,
} from "@/components/AnalysisProgress";
import { ContentCard } from "@/components/ContentCard";
import { CreatorInsightSummaryPanel } from "@/components/CreatorInsightSummaryPanel";
import { EvidenceSystemDetails } from "@/components/EvidenceSystemDetails";
import { ExecutiveInsightSnapshot } from "@/components/ExecutiveInsightSnapshot";
import { MetadataAvailabilityPanel } from "@/components/MetadataAvailabilityPanel";
import { SectionHeader } from "@/components/SectionHeader";
import { TranscriptPreviewPanel } from "@/components/TranscriptPreviewPanel";
import { VideoUrlForm } from "@/components/VideoUrlForm";
import {
  createProject,
  extractProject,
  getCreatorInsightSummary,
  getProject,
  indexProject,
} from "@/lib/api";
import {
  clearActiveProjectId,
  getActiveProjectId,
  setActiveProjectId,
} from "@/lib/app-session";
import type {
  CreatorInsightSummaryResponse,
  IndexProjectResponse,
  ProjectCreateResponse,
  ProjectDetailResponse,
} from "@/types/project";

const INITIAL_PROGRESS_STEPS: AnalysisProgressStep[] = [
  { id: "detect", label: "Detecting platforms", status: "pending" },
  { id: "extract", label: "Extracting metadata", status: "pending" },
  { id: "transcribe", label: "Pulling transcripts", status: "pending" },
  { id: "index", label: "Building evidence index", status: "pending" },
  { id: "insights", label: "Preparing creator insights", status: "pending" },
  { id: "chat", label: "Ready for AI chat", status: "pending" },
];

export function ComparisonWorkspace() {
  const searchParams = useSearchParams();
  const startNew = searchParams.get("new") === "1";
  const [content1Url, setContent1Url] = useState("");
  const [content2Url, setContent2Url] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRestoringProject, setIsRestoringProject] = useState(false);
  const [progressSteps, setProgressSteps] = useState(INITIAL_PROGRESS_STEPS);
  const [showProgress, setShowProgress] = useState(false);
  const [createdProject, setCreatedProject] =
    useState<ProjectCreateResponse | null>(null);
  const [projectDetail, setProjectDetail] =
    useState<ProjectDetailResponse | null>(null);
  const [indexResult, setIndexResult] = useState<IndexProjectResponse | null>(
    null,
  );
  const [insightSummary, setInsightSummary] =
    useState<CreatorInsightSummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [partialNotice, setPartialNotice] = useState<string | null>(null);
  const indexReady = indexResult?.status === "indexed";
  const hasResults = Boolean(projectDetail);

  const resetWorkspaceState = useCallback(() => {
    setContent1Url("");
    setContent2Url("");
    setProgressSteps(resetProgressSteps());
    setShowProgress(false);
    setCreatedProject(null);
    setProjectDetail(null);
    setIndexResult(null);
    setInsightSummary(null);
    setError(null);
    setPartialNotice(null);
  }, []);

  const restoreProject = useCallback(async (activeProjectId: string) => {
    setIsRestoringProject(true);
    setError(null);
    setPartialNotice(null);

    try {
      const [detail, summary] = await Promise.all([
        getProject(activeProjectId),
        getCreatorInsightSummary(activeProjectId).catch(() => null),
      ]);

      setProjectDetail(detail);
      setInsightSummary(summary);
      setContent1Url(detail.content_1_url ?? "");
      setContent2Url(detail.content_2_url ?? "");
      setCreatedProject({
        project_id: detail.project_id,
        status: detail.status,
        message: "Restored the current analysis session.",
      });
      setProgressSteps(restoredProgressSteps());
      setShowProgress(false);
    } catch (caughtError) {
      clearLatestProject();
      setProjectDetail(null);
      setInsightSummary(null);
      setCreatedProject(null);
      setError(getErrorMessage(caughtError));
    } finally {
      setIsRestoringProject(false);
    }
  }, []);

  useEffect(() => {
    const restoreTimer = window.setTimeout(() => {
      if (startNew) {
        clearLatestProject();
        resetWorkspaceState();
        setIsRestoringProject(false);
        return;
      }

      const latestProjectId = getActiveProjectId();

      if (!latestProjectId) {
        setIsRestoringProject(false);
        return;
      }

      void restoreProject(latestProjectId);
    }, 0);

    return () => window.clearTimeout(restoreTimer);
  }, [resetWorkspaceState, restoreProject, startNew]);

  useEffect(() => {
    if (!projectDetail) {
      return;
    }

    const hash = window.location.hash;

    if (!hash) {
      return;
    }

    const scrollTimer = window.setTimeout(() => {
      document.querySelector(hash)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 0);

    return () => window.clearTimeout(scrollTimer);
  }, [projectDetail]);

  async function handleAnalyzeContent() {
    setIsSubmitting(true);
    setShowProgress(true);
    setProgressSteps(resetProgressSteps());
    setCreatedProject(null);
    setProjectDetail(null);
    setIndexResult(null);
    setInsightSummary(null);
    setError(null);
    setPartialNotice(null);

    try {
      setProgressStatus("detect", "running");
      const created = await createProject({
        content_1_url: content1Url,
        content_2_url: content2Url,
      });
      setCreatedProject(created);
      persistLatestProject(created.project_id);
      setProgressStatus("detect", "complete");

      setProgressStatus("extract", "running");
      setProgressStatus("transcribe", "running");
      const extracted = await extractProject(created.project_id);
      setProjectDetail(extracted);
      setProgressStatus("extract", "complete");
      setProgressStatus("transcribe", "complete");

      let latestDetail = extracted;
      try {
        latestDetail = await getProject(created.project_id);
        setProjectDetail(latestDetail);
      } catch {
        setPartialNotice(
          "Analysis results are shown from the extraction response. Latest project refresh was unavailable.",
        );
      }

      setProgressStatus("index", "running");
      try {
        const nextIndexResult = await indexProject(created.project_id);
        setIndexResult(nextIndexResult);
        setProgressStatus(
          "index",
          nextIndexResult.status === "indexed" ? "complete" : "failed",
        );

        if (nextIndexResult.status !== "indexed") {
          setPartialNotice(
            nextIndexResult.message ||
              "Content was analyzed, but the evidence index is not ready yet. You can retry in Evidence & System Details.",
          );
        }
      } catch (caughtError) {
        setProgressStatus("index", "failed");
        setPartialNotice(
          `${getErrorMessage(caughtError)} You can retry in Evidence & System Details.`,
        );
      }

      setProgressStatus("insights", "running");
      try {
        const summary = await getCreatorInsightSummary(latestDetail.project_id);
        setInsightSummary(summary);
        setProgressStatus("insights", "complete");
      } catch (caughtError) {
        setProgressStatus("insights", "failed");
        setPartialNotice(
          `${getErrorMessage(caughtError)} Content cards and metadata availability remain available.`,
        );
      }

      setProgressStatus("chat", "complete");
    } catch (caughtError) {
      failRunningSteps();
      setError(getErrorMessage(caughtError));
    } finally {
      setIsSubmitting(false);
    }
  }

  function setProgressStatus(stepId: string, status: ProgressStatus) {
    setProgressSteps((currentSteps) =>
      currentSteps.map((step) =>
        step.id === stepId ? { ...step, status } : step,
      ),
    );
  }

  function failRunningSteps() {
    setProgressSteps((currentSteps) =>
      currentSteps.map((step) =>
        step.status === "running" ? { ...step, status: "failed" } : step,
      ),
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      <section className="mx-auto max-w-7xl px-6 py-12 sm:px-8 lg:px-10">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_430px]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
              Analyze
            </p>
            <h1 className="mt-3 text-4xl font-semibold leading-tight text-slate-950 dark:text-slate-50">
              Analyze two pieces of short-form content
            </h1>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600 dark:text-slate-300 sm:text-base">
              Paste any supported YouTube, Instagram, or Facebook short-form URLs.
              CreatorLens AI will detect platforms, extract public metadata,
              build evidence, and prepare creator insights.
            </p>

            <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                Best-effort extraction with clear limits
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Confirmed public metrics are shown when available. Unavailable
                fields are not estimated.
              </p>
            </div>
          </div>

          <VideoUrlForm
            content1Url={content1Url}
            content2Url={content2Url}
            setContent1Url={setContent1Url}
            setContent2Url={setContent2Url}
            onSubmit={handleAnalyzeContent}
            isSubmitting={isSubmitting}
          />
        </div>

        <div className="mt-8 grid gap-4">
          <AnalysisProgress steps={progressSteps} isVisible={showProgress} />

          {isRestoringProject ? (
            <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100">
              Restoring the current analysis session...
            </p>
          ) : null}

          {createdProject ? (
            <p className="rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900 dark:border-teal-800 dark:bg-teal-950 dark:text-teal-100">
              {hasResults
                ? "Current analysis session is loaded from your analyzed URLs."
                : "Comparison created. CreatorLens AI is organizing public evidence for Content 1 and Content 2."}
            </p>
          ) : null}

          {partialNotice ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
              {partialNotice}
            </p>
          ) : null}

          {error ? (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-100">
              {error}
            </p>
          ) : null}
        </div>

        <section className="mt-10 grid gap-4">
          <ExecutiveInsightSnapshot
            summary={insightSummary}
            isLoading={isSubmitting}
          />
        </section>

        <section className="mt-8">
          <SectionHeader
            eyebrow="Content overview"
            title="Extracted public metadata and transcript signals"
            text="Each card separates confirmed public metrics from unavailable fields so the comparison stays honest."
          />
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
          </div>
        </section>

        {hasResults ? (
          <>
            <section className="mt-4 grid gap-4">
              <MetadataAvailabilityPanel projectId={projectDetail?.project_id ?? null} />
            </section>

            <section id="insights" className="mt-4 grid gap-4">
              <CreatorInsightSummaryPanel
                projectId={projectDetail?.project_id ?? null}
                indexReady={indexReady}
                initialSummary={insightSummary}
                onSummaryLoaded={setInsightSummary}
              />
            </section>

            <section id="chat" className="mt-4 rounded-2xl border border-teal-200 bg-white p-6 shadow-md shadow-teal-900/5 dark:border-teal-900 dark:bg-slate-900">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700 dark:text-teal-300">
                    Streaming creator chat
                  </p>
                  <h2 className="mt-2 text-xl font-semibold text-slate-950 dark:text-slate-50">
                    Continue in the dedicated assistant workspace
                  </h2>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                    Ask performance, hook, rewrite, and improvement questions
                    grounded in cited metadata, transcripts, and creator insights.
                  </p>
                </div>
                <Link
                  href="/chat"
                  className="inline-flex h-11 items-center justify-center rounded-md bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-teal-400 dark:text-slate-950 dark:hover:bg-teal-300"
                >
                  Open Creator Chat
                </Link>
              </div>
            </section>

            <section id="evidence" className="mt-4 grid gap-4">
              <EvidenceSystemDetails
                projectId={projectDetail?.project_id ?? null}
                indexResult={indexResult}
                indexReady={indexReady}
                onIndexed={setIndexResult}
              />
            </section>

            <details className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <summary className="cursor-pointer list-none">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700 dark:text-teal-300">
                  Transcript Evidence
                </p>
                <h2 className="mt-2 text-base font-semibold text-slate-950 dark:text-slate-50">
                  Preview extracted transcript segments
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                  Optional evidence review for multilingual captions and
                  best-effort transcription.
                </p>
              </summary>
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <TranscriptPreviewPanel
                  projectId={projectDetail?.project_id ?? null}
                  item={contentItem(projectDetail, "content_1")}
                  label="Content 1"
                />
                <TranscriptPreviewPanel
                  projectId={projectDetail?.project_id ?? null}
                  item={contentItem(projectDetail, "content_2")}
                  label="Content 2"
                />
              </div>
            </details>
          </>
        ) : (
          <EmptyState />
        )}
      </section>
    </main>
  );
}

function EmptyState() {
  return (
    <section className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center dark:border-slate-700 dark:bg-slate-900">
      <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
        Your comparison workspace is ready.
      </p>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">
        Paste Content URL 1 and Content URL 2, then analyze to see content cards,
        metadata availability, cited insights, and advanced evidence controls.
      </p>
    </section>
  );
}

function resetProgressSteps(): AnalysisProgressStep[] {
  return INITIAL_PROGRESS_STEPS.map((step) => ({
    ...step,
    status: "pending",
  }));
}

function restoredProgressSteps(): AnalysisProgressStep[] {
  return INITIAL_PROGRESS_STEPS.map((step) => ({
    ...step,
    status: "complete",
  }));
}

function contentItem(
  projectDetail: ProjectDetailResponse | null,
  slot: "content_1" | "content_2",
) {
  return (
    projectDetail?.content_items.find((item) => item.slot === slot) ?? null
  );
}

function persistLatestProject(projectId: string) {
  if (typeof window === "undefined") {
    return;
  }

  setActiveProjectId(projectId);
}

function clearLatestProject() {
  if (typeof window === "undefined") {
    return;
  }

  clearActiveProjectId();
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}
