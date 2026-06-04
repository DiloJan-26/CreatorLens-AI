"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CreatorChatPanel } from "@/components/CreatorChatPanel";
import { getCreatorInsightSummary, getProject } from "@/lib/api";
import { getActiveProjectId } from "@/lib/app-session";
import type {
  ContentItem,
  CreatorInsightSummaryResponse,
  ProjectDetailResponse,
} from "@/types/project";

export function CreatorChatPage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projectDetail, setProjectDetail] =
    useState<ProjectDetailResponse | null>(null);
  const [summary, setSummary] =
    useState<CreatorInsightSummaryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadProject = useCallback(async (activeProjectId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const [detail, insightSummary] = await Promise.all([
        getProject(activeProjectId),
        getCreatorInsightSummary(activeProjectId).catch(() => null),
      ]);
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

  if (!projectId) {
    return (
      <main className="min-h-screen bg-slate-50 px-6 py-12 text-slate-950 dark:bg-slate-950 dark:text-slate-50 sm:px-8 lg:px-10">
        <EmptyChatState />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      <section className="mx-auto max-w-7xl px-6 py-10 sm:px-8 lg:px-10">
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
            Cited Creator Reasoning
          </p>
          <h1 className="mt-3 text-4xl font-semibold leading-tight text-slate-950 dark:text-slate-50">
            Ask CreatorLens AI
          </h1>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600 dark:text-slate-300 sm:text-base">
            Ask performance, hook, rewrite, and improvement questions grounded
            in cited metadata, transcripts, and creator insights.
          </p>
        </div>

        {isLoading ? (
          <p className="rounded-2xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100">
            Loading the latest creator intelligence workspace...
          </p>
        ) : null}

        {error ? (
          <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100">
            {error}
          </p>
        ) : null}

        {!isLoading && projectDetail ? (
          <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
            <aside className="grid gap-4 lg:sticky lg:top-[96px] lg:self-start">
              <ProjectContextCard
                projectId={projectId}
                projectDetail={projectDetail}
                summary={summary}
              />
              <Link
                href="/analyze?new=1"
                className="inline-flex h-11 items-center justify-center rounded-md border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-teal-300 hover:bg-teal-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                Analyze New Content
              </Link>
            </aside>

            <CreatorChatPanel projectId={projectId} indexReady={true} />
          </div>
        ) : null}
      </section>
    </main>
  );
}

function EmptyChatState() {
  return (
    <section className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
        Creator chat
      </p>
      <h1 className="mt-3 text-3xl font-semibold text-slate-950 dark:text-slate-50">
        Analyze two content URLs first to start a cited creator chat.
      </h1>
      <p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300">
        CreatorLens AI only opens chat for an explicit analyzed project. Start
        from the analysis workspace so the sidebar and answers use real extracted
        data from your URLs.
      </p>
      <Link
        href="/analyze?new=1"
        className="mt-6 inline-flex h-11 items-center justify-center rounded-md bg-slate-950 px-5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-teal-400 dark:text-slate-950"
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
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700 dark:text-teal-300">
        Current project
      </p>
      <p className="mt-2 break-all text-xs text-slate-500 dark:text-slate-400">
        {projectId}
      </p>

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
        <p className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-6 text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
          Project content is not loaded yet.
        </p>
      )}
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

  const contentText = item.title || item.creator || item.creator_handle || item.url;

  return (
    <article className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950">
      <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-50">
        {platformLabel(item.platform)}
      </p>
      {contentText ? (
        <p className="mt-1 line-clamp-3 break-words text-xs leading-5 text-slate-600 dark:text-slate-300">
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
      <dt className="font-medium text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="mt-1 break-words text-slate-950 dark:text-slate-50">
        {value}
      </dd>
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
