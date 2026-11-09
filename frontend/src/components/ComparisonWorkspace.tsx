"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  type AnalysisProgressStep,
  type ProgressStatus,
} from "@/components/AnalysisProgress";
import { AiReasoningStatus } from "./AiReasoningStatus";
import { ContentCard } from "@/components/ContentCard";
import { CreatorInsightSummaryPanel } from "@/components/CreatorInsightSummaryPanel";
import { EvidenceSystemDetails } from "@/components/EvidenceSystemDetails";
import { ExecutiveInsightSnapshot } from "@/components/ExecutiveInsightSnapshot";
import { IngestionProgressPanel } from "@/components/IngestionProgressPanel";
import { MetadataAvailabilityPanel } from "@/components/MetadataAvailabilityPanel";
import { PageHeading, Notice } from "./ui";
import { TranscriptPreviewPanel } from "@/components/TranscriptPreviewPanel";
import { VideoUrlForm } from "@/components/VideoUrlForm";
import {
  createProject,
  getCreatorInsightSummary,
  getProject,
  getProjectIngestionStatus,
  startProjectIngestion,
} from "@/lib/api";
import {
  clearActiveProjectId,
  getActiveProjectId,
  setActiveProjectId,
} from "@/lib/app-session";
import type {
  CreatorInsightSummaryResponse,
  IndexProjectResponse,
  IngestionJobStatus,
  IngestionStatusResponse,
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
  const [activeTab, setActiveTab] = useState("overview");
  useEffect(() => {
    const sync = () => {
      const hash = window.location.hash.slice(1);
      setActiveTab(
        ["overview", "insights", "evidence", "transcript", "chat"].includes(
          hash,
        )
          ? hash
          : "overview",
      );
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const startNew = searchParams.get("new") === "1";
  const [content1Url, setContent1Url] = useState("");
  const [content2Url, setContent2Url] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRestoringProject, setIsRestoringProject] = useState(false);
  const [, setProgressSteps] = useState(INITIAL_PROGRESS_STEPS);
  const [, setShowProgress] = useState(false);
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
  const [ingestionStatus, setIngestionStatus] =
    useState<IngestionStatusResponse | null>(null);
  const [activeIngestion, setActiveIngestion] = useState<{
    projectId: string;
    jobId: string;
  } | null>(null);
  const indexReady =
    indexResult?.status === "indexed" ||
    ingestionStatus?.status === "READY" ||
    ingestionStatus?.status === "PARTIAL_READY";
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
    setIngestionStatus(null);
    setActiveIngestion(null);
  }, []);

  const restoreProject = useCallback(async (activeProjectId: string) => {
    setIsRestoringProject(true);
    setError(null);
    setPartialNotice(null);

    try {
      const [detail, summary, latestIngestion] = await Promise.all([
        getProject(activeProjectId),
        getCreatorInsightSummary(activeProjectId).catch(() => null),
        getProjectIngestionStatus(activeProjectId).catch(() => null),
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
      setIngestionStatus(latestIngestion);

      if (latestIngestion && !isTerminalStatus(latestIngestion.status)) {
        setProgressSteps(progressStepsForIngestion(latestIngestion.status));
        setShowProgress(true);
        setIsSubmitting(true);
        setActiveIngestion({
          projectId: activeProjectId,
          jobId: latestIngestion.job_id,
        });
      } else if (latestIngestion) {
        setProgressSteps(progressStepsForIngestion(latestIngestion.status));
        setShowProgress(true);

        if (latestIngestion.status === "FAILED") {
          setError(
            latestIngestion.error_message ??
              "The latest background ingestion job failed.",
          );
        } else if (latestIngestion.status === "PARTIAL_READY") {
          setPartialNotice(
            "The restored analysis contains partial evidence. Unavailable fields remain clearly marked.",
          );
        }
      } else {
        setProgressSteps(restoredProgressSteps());
        setShowProgress(false);
      }
    } catch (caughtError) {
      clearActiveProjectId();
      setProjectDetail(null);
      setInsightSummary(null);
      setCreatedProject(null);
      setError(getErrorMessage(caughtError));
    } finally {
      setIsRestoringProject(false);
    }
  }, []);

  useEffect(() => {
    if (!activeIngestion) {
      return;
    }

    const ingestion = activeIngestion;
    const controller = new AbortController();
    let pollTimer: number | null = null;
    let consecutiveFailures = 0;

    async function poll() {
      try {
        const latest = await getProjectIngestionStatus(
          ingestion.projectId,
          ingestion.jobId,
          { signal: controller.signal },
        );

        if (controller.signal.aborted) {
          return;
        }

        consecutiveFailures = 0;
        setIngestionStatus(latest);
        setProgressSteps(progressStepsForIngestion(latest.status));

        if (!isTerminalStatus(latest.status)) {
          pollTimer = window.setTimeout(poll, 2000);
          return;
        }

        if (latest.status === "FAILED") {
          setError(
            latest.error_message ??
              "Background ingestion failed. Check the worker logs and try again.",
          );
          setIsSubmitting(false);
          setActiveIngestion(null);
          return;
        }

        const [detail, summary] = await Promise.all([
          getProject(ingestion.projectId),
          getCreatorInsightSummary(ingestion.projectId).catch(() => null),
        ]);

        if (controller.signal.aborted) {
          return;
        }

        setProjectDetail(detail);
        setInsightSummary(summary);
        setContent1Url(detail.content_1_url ?? "");
        setContent2Url(detail.content_2_url ?? "");
        setProgressSteps(
          summary
            ? restoredProgressSteps()
            : restoredProgressSteps().map((step) =>
                step.id === "insights" ? { ...step, status: "failed" } : step,
              ),
        );

        if (latest.status === "PARTIAL_READY") {
          setPartialNotice(
            "The analysis is ready with partial evidence. Unavailable metadata or transcript fields remain clearly marked.",
          );
        } else if (!summary) {
          setPartialNotice(
            "The evidence index is ready, but the creator insight summary could not be loaded. Content, evidence, and chat remain available.",
          );
        }

        setIsSubmitting(false);
        setActiveIngestion(null);
      } catch (caughtError) {
        if (controller.signal.aborted) {
          return;
        }

        consecutiveFailures += 1;
        if (consecutiveFailures < 3) {
          pollTimer = window.setTimeout(poll, 3000);
          return;
        }

        setError(
          `${getErrorMessage(caughtError)} Automatic status checks stopped after three attempts. Refresh the page to resume.`,
        );
        setIsSubmitting(false);
        setActiveIngestion(null);
      }
    }

    void poll();

    return () => {
      controller.abort();
      if (pollTimer !== null) {
        window.clearTimeout(pollTimer);
      }
    };
  }, [activeIngestion]);

  useEffect(() => {
    const restoreTimer = window.setTimeout(() => {
      if (startNew) {
        clearActiveProjectId();
        resetWorkspaceState();
        // Consume this one-time action so a later reload restores the new project.
        window.history.replaceState(null, "", "/analyze");
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
    setIngestionStatus(null);
    setActiveIngestion(null);

    try {
      setProgressStatus("detect", "running");
      const created = await createProject({
        content_1_url: content1Url,
        content_2_url: content2Url,
      });
      setCreatedProject(created);
      persistLatestProject(created.project_id);
      setProgressStatus("detect", "complete");

      const started = await startProjectIngestion(created.project_id);
      setActiveIngestion({
        projectId: created.project_id,
        jobId: started.job_id,
      });
    } catch (caughtError) {
      failRunningSteps();
      setError(getErrorMessage(caughtError));
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
    <main className="page-container comparison-workspace">
      <PageHeading
        eyebrow="Creator workspace"
        title={hasResults ? "Your comparison" : "Compare two videos"}
        description={
          hasResults
            ? "Review the evidence, understand the differences, and decide what to test next."
            : "Bring two public videos. We'll bring the evidence."
        }
        action={
          hasResults ? (
            <button
              className="button-secondary"
              onClick={() => {
                clearLatestProject();
                resetWorkspaceState();
                setActiveTab("overview");
                window.history.replaceState(null, "", "/analyze?new=1");
              }}
            >
              New comparison
            </button>
          ) : undefined
        }
      />
      {!hasResults && !isRestoringProject && (
        <>
          <VideoUrlForm
            content1Url={content1Url}
            content2Url={content2Url}
            setContent1Url={setContent1Url}
            setContent2Url={setContent2Url}
            onSubmit={handleAnalyzeContent}
            isSubmitting={isSubmitting}
          />
          <p className="muted text-sm mt-5 max-w-3xl">
            Extraction is best-effort. Missing public metrics are never
            estimated. Comparing different platforms or audiences provides
            context, not proof of what caused performance.
          </p>
        </>
      )}
      <div className="grid gap-4 my-6">
        {isRestoringProject && <Notice>Restoring your comparison...</Notice>}
        {createdProject && !hasResults && !ingestionStatus && (
          <Notice>Comparison created. Waiting for processing status...</Notice>
        )}
        {hasResults && ingestionStatus?.status === "READY" ? (
          <details className="text-sm muted">
            <summary>Analysis ready / Processing details</summary>
            <IngestionProgressPanel
              status={ingestionStatus}
              isPolling={false}
            />
          </details>
        ) : (
          <IngestionProgressPanel
            status={ingestionStatus}
            isPolling={Boolean(activeIngestion)}
          />
        )}
        {partialNotice && <Notice tone="warning">{partialNotice}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
      </div>
      {hasResults && (
        <>
          <nav className="section-tabs" aria-label="Comparison sections">
            {[
              ["overview", "Overview"],
              ["insights", "Insights"],
              ["evidence", "Evidence"],
              ["transcript", "Transcript"],
              ["chat", "Ask AI"],
            ].map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                aria-current={activeTab === id ? "location" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  window.history.pushState(null, "", `#${id}`);
                  setActiveTab(id);
                }}
              >
                {label}
              </a>
            ))}
          </nav>
          <section
            id="overview"
            hidden={activeTab !== "overview"}
            className="section-panel"
          >
            <ExecutiveInsightSnapshot
              summary={insightSummary}
              isLoading={isSubmitting}
            />
            <div className="grid gap-5 mt-6 xl:grid-cols-2">
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
          <section
            id="insights"
            hidden={activeTab !== "insights"}
            className="section-panel"
          >
            <CreatorInsightSummaryPanel
              projectId={projectDetail?.project_id ?? null}
              indexReady={indexReady}
              initialSummary={insightSummary}
              onSummaryLoaded={setInsightSummary}
            />
            <details className="technical-details">
              <summary>AI connection diagnostic</summary>
              <p className="muted text-xs mb-3">
                The Check action sends a model test request. It may consume
                provider quota.
              </p>
              <AiReasoningStatus />
            </details>
          </section>
          <section
            id="evidence"
            hidden={activeTab !== "evidence"}
            className="section-panel grid gap-5"
          >
            <EvidenceSystemDetails
              projectId={projectDetail?.project_id ?? null}
              indexResult={indexResult}
              indexReady={indexReady}
              onIndexed={setIndexResult}
            />
            <MetadataAvailabilityPanel
              projectId={projectDetail?.project_id ?? null}
            />
          </section>
          <section
            id="transcript"
            hidden={activeTab !== "transcript"}
            className="section-panel"
          >
            <h2 className="text-xl mb-2">Read the original evidence</h2>
            <p className="muted mb-5">
              Captions and transcriptions may contain errors. Review language,
              source and timestamps before interpreting a passage.
            </p>
            <div className="grid gap-5 xl:grid-cols-2">
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
          </section>
          <section
            id="chat"
            hidden={activeTab !== "chat"}
            className="section-panel ui-panel"
          >
            <h2 className="text-xl">Ask the evidence a question</h2>
            <p className="muted mt-3 mb-5">
              Compare opening hooks, explore the metrics, or ask what to
              improve. The assistant uses this active comparison and returns
              supporting citations.
            </p>
            <Link href="/chat" className="button-primary">
              Open AI Assistant
            </Link>
          </section>
        </>
      )}
    </main>
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

function isTerminalStatus(status: IngestionJobStatus): boolean {
  return (
    status === "READY" || status === "PARTIAL_READY" || status === "FAILED"
  );
}

function progressStepsForIngestion(
  status: IngestionJobStatus,
): AnalysisProgressStep[] {
  if (status === "READY" || status === "PARTIAL_READY") {
    return restoredProgressSteps();
  }

  if (status === "FAILED") {
    return INITIAL_PROGRESS_STEPS.map((step) => ({
      ...step,
      status:
        step.id === "detect"
          ? "complete"
          : step.id === "insights" || step.id === "chat"
            ? "pending"
            : "failed",
    }));
  }

  const completed = new Set<string>(["detect"]);
  let runningStep: string | null = status === "PENDING" ? null : "extract";

  if (status === "EXTRACTING_TRANSCRIPT") {
    completed.add("extract");
    runningStep = "transcribe";
  } else if (
    status === "CHUNKING" ||
    status === "EMBEDDING" ||
    status === "INDEXING"
  ) {
    completed.add("extract");
    completed.add("transcribe");
    runningStep = "index";
  }

  return INITIAL_PROGRESS_STEPS.map((step) => ({
    ...step,
    status: completed.has(step.id)
      ? "complete"
      : runningStep !== null && step.id === runningStep
        ? "running"
        : "pending",
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
