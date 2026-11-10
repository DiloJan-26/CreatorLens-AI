"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PageHeading, Notice } from "./ui";
import { PlatformIcon } from "./PlatformIcon";
import { CreatorChatPanel } from "@/components/CreatorChatPanel";
import {
  getCreatorInsightSummary,
  getProject,
  getProjectIngestionStatus,
} from "@/lib/api";
import { getActiveProjectId } from "@/lib/app-session";
import type {
  ContentItem,
  CreatorInsightSummaryResponse,
  ProjectDetailResponse,
} from "@/types/project";

export function CreatorChatPage() {
  const [contextOpen, setContextOpen] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(min-width:1280px)");
    const sync = () => setContextOpen(media.matches);
    const timer = window.setTimeout(sync, 0);
    media.addEventListener("change", sync);
    return () => {
      window.clearTimeout(timer);
      media.removeEventListener("change", sync);
    };
  }, []);
  const [readiness, setReadiness] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectDetail, setProjectDetail] =
    useState<ProjectDetailResponse | null>(null);
  const [summary, setSummary] = useState<CreatorInsightSummaryResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProject = useCallback(async (activeProjectId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const [detail, insightSummary, status] = await Promise.all([
        getProject(activeProjectId),
        getCreatorInsightSummary(activeProjectId).catch(() => null),
        getProjectIngestionStatus(activeProjectId).catch(() => null),
      ]);
      setReadiness(status?.status ?? null);
      setProjectDetail(detail);
      setSummary(insightSummary);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
      setProjectDetail(null);
      setSummary(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const activeProjectId = getActiveProjectId();

    if (!activeProjectId) {
      const emptyTimer = window.setTimeout(() => {
        setProjectId(null);
        setProjectDetail(null);
        setSummary(null);
        setError(null);
        setIsLoading(false);
      }, 0);

      return () => window.clearTimeout(emptyTimer);
    }

    const loadTimer = window.setTimeout(() => {
      setProjectId(activeProjectId);
      void loadProject(activeProjectId);
    }, 0);

    return () => window.clearTimeout(loadTimer);
  }, [loadProject]);

  if (!projectId)
    return (
      <main className="page-container">
        {isLoading ? (
          <Notice>Loading your workspace...</Notice>
        ) : (
          <EmptyChatState />
        )}
      </main>
    );
  return (
    <main className="page-container assistant-page">
      <PageHeading
        eyebrow="Creator workspace"
        title="CreatorLens AI Assistant"
        icon="chat"
        description="Ask a focused question. Follow the evidence."
        action={
          <Link className="button-secondary" href="/analyze">
            View comparison
          </Link>
        }
      />
      {isLoading && <Notice>Loading comparison context...</Notice>}
      {error && (
        <Notice tone="error">
          {error}{" "}
          <button
            className="button-secondary"
            onClick={() => void loadProject(projectId)}
          >
            Retry
          </button>
        </Notice>
      )}
      {!isLoading && projectDetail && (
        <div className="chat-layout">
          <aside className="chat-context">
            {readiness && readiness !== "READY" && (
              <p className="notice text-sm mb-3">
                {readiness === "PARTIAL_READY"
                  ? "Partial evidence available. Review missing fields before drawing conclusions."
                  : `Processing status: ${readiness.replace(/_/g, " ").toLowerCase()}. Return to Compare for updates.`}
              </p>
            )}
            <details
              className="context-disclosure"
              open={contextOpen}
              onToggle={(e) => setContextOpen(e.currentTarget.open)}
            >
              <summary>Active comparison</summary>
              <ProjectContextCard
                projectId={projectId}
                projectDetail={projectDetail}
                summary={summary}
              />
              <Link className="button-quiet" href="/analyze#evidence">
                Inspect evidence
              </Link>
            </details>
            <p className="muted text-xs mt-4">
              AI suggestions are hypotheses to test. Missing public metrics are
              not estimated.
            </p>
          </aside>
          <CreatorChatPanel
            projectId={projectId}
            indexReady={
              readiness === null ||
              readiness === "READY" ||
              readiness === "PARTIAL_READY"
            }
          />
        </div>
      )}
    </main>
  );
}

function EmptyChatState() {
  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
        Creator chat
      </p>
      <h1 className="mt-3 text-3xl font-semibold text-slate-950">
        Analyze two content URLs first to start a cited creator chat.
      </h1>
      <p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-slate-600">
        CreatorLens AI only opens chat for an explicit analyzed project. Start
        from the analysis workspace so the sidebar and answers use real
        extracted data from your URLs.
      </p>
      <Link
        href="/analyze?new=1"
        className="mt-6 inline-flex h-11 items-center justify-center rounded-md bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-slate-800"
      >
        Go to Analysis
      </Link>
    </section>
  );
}

function ProjectContextCard({
  projectId,
  projectDetail,
  summary,
}: {
  projectId: string;
  projectDetail: ProjectDetailResponse;
  summary: CreatorInsightSummaryResponse | null;
}) {
  const content1 = contentItem(projectDetail, "content_1");
  const content2 = contentItem(projectDetail, "content_2");
  const hasContent = Boolean(content1 || content2);

  return (
    <section className="chat-context-card">
      {hasContent ? (
        <div className="mt-5 grid gap-3">
          <ContentSummary
            label="Content 1"
            item={content1}
            insight={summary?.content_1 ?? null}
          />
          <ContentSummary
            label="Content 2"
            item={content2}
            insight={summary?.content_2 ?? null}
          />
        </div>
      ) : (
        <p className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-6 text-slate-600">
          Project content is not loaded yet.
        </p>
      )}
      <details className="technical-details">
        <summary>Project identifier</summary>
        <p className="break-all text-xs muted">{projectId}</p>
      </details>
    </section>
  );
}

function ContentSummary({
  label,
  item,
  insight,
}: {
  label: "Content 1" | "Content 2";
  item: ContentItem | null;
  insight: NonNullable<CreatorInsightSummaryResponse["content_1"]> | null;
}) {
  if (!item) {
    return null;
  }

  const contentText =
    item.title || item.creator || item.creator_handle || item.url;

  return (
    <article className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <p className="platform-label">
        <PlatformIcon platform={item.platform} size={17} />
        {label} / {platformLabel(item.platform)}
      </p>
      {contentText ? (
        <p className="mt-1 line-clamp-3 break-words text-xs leading-5 text-slate-600">
          {contentText}
        </p>
      ) : null}
      {insight ? (
        <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
          <ContextMetric
            label="Hook score"
            value={`${insight.hook_analysis.hook_score}/10`}
          />
          <ContextMetric
            label="Creator Insight Score"
            value={`${insight.scores.overall_score}/10`}
          />
        </dl>
      ) : null}
    </article>
  );
}

function ContextMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-950">{value}</dd>
    </div>
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

function platformLabel(platform: string): string {
  if (platform === "youtube") {
    return "YouTube";
  }

  if (platform === "instagram") {
    return "Instagram";
  }

  if (platform === "facebook") {
    return "Facebook";
  }

  return platform;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not load the creator chat workspace.";
}
