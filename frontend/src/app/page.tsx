"use client";

import { useRef, useState } from "react";

import {
  AnalysisProgress,
  type AnalysisProgressStep,
  type ProgressStatus,
} from "@/components/AnalysisProgress";
import { ContentCard } from "@/components/ContentCard";
import { CreatorChatPanel } from "@/components/CreatorChatPanel";
import { CreatorInsightSummaryPanel } from "@/components/CreatorInsightSummaryPanel";
import { EvidenceSystemDetails } from "@/components/EvidenceSystemDetails";
import { ExecutiveInsightSnapshot } from "@/components/ExecutiveInsightSnapshot";
import { FeatureGrid } from "@/components/FeatureGrid";
import { LandingHero } from "@/components/LandingHero";
import { MetadataAvailabilityPanel } from "@/components/MetadataAvailabilityPanel";
import { TranscriptPreviewPanel } from "@/components/TranscriptPreviewPanel";
import { VideoUrlForm } from "@/components/VideoUrlForm";
import { WorkflowStrip } from "@/components/WorkflowStrip";
import {
  createProject,
  extractProject,
  getCreatorInsightSummary,
  getProject,
  indexProject,
} from "@/lib/api";
import type {
  CreatorInsightSummaryResponse,
  IndexProjectResponse,
  ProjectCreateResponse,
  ProjectDetailResponse,
} from "@/types/project";

const INITIAL_PROGRESS_STEPS: AnalysisProgressStep[] = [
  { id: "create", label: "Creating comparison", status: "pending" },
  { id: "detect", label: "Detecting platforms", status: "pending" },
  { id: "extract", label: "Extracting metadata", status: "pending" },
  { id: "transcribe", label: "Pulling/transcribing audio", status: "pending" },
  { id: "index", label: "Building evidence index", status: "pending" },
  { id: "insights", label: "Generating creator insights", status: "pending" },
];

export default function Home() {
  const workspaceRef = useRef<HTMLElement | null>(null);
  const [content1Url, setContent1Url] = useState("");
  const [content2Url, setContent2Url] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
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

  function scrollToWorkspace() {
    workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

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
    scrollToWorkspace();

    try {
      setProgressStatus("create", "running");
      const created = await createProject({
        content_1_url: content1Url,
        content_2_url: content2Url,
      });
      setCreatedProject(created);
      setProgressStatus("create", "complete");
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
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <Header onStart={scrollToWorkspace} />
      <LandingHero onStart={scrollToWorkspace} />
      <FeatureGrid />
      <WorkflowStrip />

      <section
        id="demo"
        ref={workspaceRef}
        className="mx-auto max-w-7xl px-6 py-16 sm:px-8 lg:px-10"
      >
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
              Compare Content
            </p>
            <h2 className="mt-3 text-3xl font-semibold text-slate-950">
              Paste two URLs and get a cited creator review.
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600 sm:text-base">
              CreatorLens AI handles the normal workflow in one click: project
              creation, platform detection, best-effort extraction, multilingual
              transcripts, evidence indexing, and creator insights.
            </p>

            <div className="mt-6 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-sm font-semibold text-slate-950">
                Best-effort public extraction
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                Confirmed public metrics are shown when available. Unavailable
                fields are marked clearly and are not estimated.
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

          {createdProject ? (
            <p className="rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-teal-900">
              Comparison created. CreatorLens AI is organizing public evidence
              for Content 1 and Content 2.
            </p>
          ) : null}

          {partialNotice ? (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-900">
              {partialNotice}
            </p>
          ) : null}

          {error ? (
            <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm leading-6 text-rose-800">
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

        <section className="mt-4">
          <SectionHeader
            eyebrow="Content Overview"
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

            <section className="mt-4 grid gap-4">
              <CreatorInsightSummaryPanel
                projectId={projectDetail?.project_id ?? null}
                indexReady={indexReady}
                initialSummary={insightSummary}
                onSummaryLoaded={setInsightSummary}
              />
            </section>

            <section className="mt-4 grid gap-4">
              <CreatorChatPanel
                projectId={projectDetail?.project_id ?? null}
                indexReady={indexReady}
              />
            </section>

            <section className="mt-4 grid gap-4">
              <EvidenceSystemDetails
                projectId={projectDetail?.project_id ?? null}
                indexResult={indexResult}
                indexReady={indexReady}
                onIndexed={setIndexResult}
              />
            </section>

            <details className="mt-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <summary className="cursor-pointer list-none">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
                  Transcript Evidence
                </p>
                <h2 className="mt-2 text-base font-semibold text-slate-950">
                  Preview extracted transcript segments
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
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

      <footer className="border-t border-slate-200 bg-white px-6 py-8 sm:px-8 lg:px-10">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-semibold text-slate-950">CreatorLens AI</p>
          <p>
            Best-effort public extraction. Confirmed public metrics only.
            Unavailable fields are not estimated.
          </p>
        </div>
      </footer>
    </main>
  );
}

function Header({ onStart }: { onStart: () => void }) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-[76px] max-w-7xl items-center justify-between gap-4 px-6 sm:px-8 lg:px-10">
        <a href="#" className="text-base font-semibold text-slate-950">
          CreatorLens AI
        </a>
        <nav className="hidden items-center gap-6 text-sm font-medium text-slate-600 md:flex">
          <a className="transition hover:text-slate-950" href="#how-it-works">
            How it works
          </a>
          <a className="transition hover:text-slate-950" href="#insights">
            Insights
          </a>
          <a className="transition hover:text-slate-950" href="#demo">
            Demo
          </a>
          <a className="transition hover:text-slate-950" href="#evidence">
            Evidence
          </a>
        </nav>
        <button
          type="button"
          onClick={onStart}
          className="inline-flex h-10 items-center justify-center rounded-md bg-slate-950 px-4 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          Start Analysis
        </button>
      </div>
    </header>
  );
}

function SectionHeader({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <div className="max-w-3xl">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
        {eyebrow}
      </p>
      <h2 className="mt-2 text-2xl font-semibold text-slate-950">{title}</h2>
      <p className="mt-3 text-sm leading-7 text-slate-600">{text}</p>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="mt-4 rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center">
      <p className="text-sm font-semibold text-slate-950">
        Your comparison workspace is ready.
      </p>
      <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-slate-600">
        Paste Content URL 1 and Content URL 2, then analyze to see content
        cards, metadata availability, cited insights, chat, and advanced
        evidence controls.
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
