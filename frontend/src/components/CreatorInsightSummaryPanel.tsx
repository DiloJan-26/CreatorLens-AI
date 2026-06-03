"use client";

import { useCallback, useEffect, useState } from "react";

import { getCreatorInsightSummary } from "@/lib/api";
import type {
  ComparisonInsight,
  CreatorInsightSummaryResponse,
} from "@/types/project";

import { HookComparisonCard } from "./HookComparisonCard";
import { InsightScoreCard } from "./InsightScoreCard";
import { RecommendationList } from "./RecommendationList";

type CreatorInsightSummaryPanelProps = {
  projectId: string | null;
  indexReady?: boolean;
  initialSummary?: CreatorInsightSummaryResponse | null;
  onSummaryLoaded?: (summary: CreatorInsightSummaryResponse) => void;
};

export function CreatorInsightSummaryPanel({
  projectId,
  indexReady = false,
  initialSummary = null,
  onSummaryLoaded,
}: CreatorInsightSummaryPanelProps) {
  const [summary, setSummary] =
    useState<CreatorInsightSummaryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const visibleSummary = summary ?? initialSummary;
  const activeSummary =
    projectId && visibleSummary?.project_id === projectId ? visibleSummary : null;

  const loadInsights = useCallback(
    async (activeProjectId: string) => {
      setIsLoading(true);
      setError(null);

      try {
        const nextSummary = await getCreatorInsightSummary(activeProjectId);
        setSummary(nextSummary);
        onSummaryLoaded?.(nextSummary);
      } catch (caughtError) {
        setSummary(null);
        setError(getErrorMessage(caughtError));
      } finally {
        setIsLoading(false);
      }
    },
    [onSummaryLoaded],
  );

  useEffect(() => {
    if (!projectId) {
      return;
    }

    if (initialSummary?.project_id === projectId) {
      return;
    }

    const loadTimer = window.setTimeout(() => {
      void loadInsights(projectId);
    }, 0);

    return () => window.clearTimeout(loadTimer);
  }, [initialSummary?.project_id, loadInsights, projectId]);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Creator intelligence
          </p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">
            Creator Insight Summary
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            CreatorLens AI compares hooks, captions, confirmed public metrics,
            and metadata completeness to explain what may improve the next post.
          </p>
        </div>
        <button
          type="button"
          onClick={() => projectId && void loadInsights(projectId)}
          disabled={!projectId || isLoading}
          className="inline-flex h-10 items-center justify-center rounded-md bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isLoading ? "Refreshing..." : "Refresh Insights"}
        </button>
      </div>

      <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-600">
        Scores are heuristic review signals, not guaranteed performance
        predictions.
        {!indexReady ? " Vector search is not required for this summary." : ""}
      </p>

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {!projectId ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Creator Insight Summary appears after Content 1 and Content 2 are analyzed.
        </p>
      ) : null}

      {isLoading && !activeSummary ? (
        <p className="mt-4 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Loading Creator Insight Summary...
        </p>
      ) : null}

      {activeSummary ? (
        <div className="mt-5 grid gap-4">
          <OverallComparisonCard comparison={activeSummary.comparison} />

          <div className="grid gap-4 lg:grid-cols-2">
            {activeSummary.content_1 ? (
              <InsightScoreCard content={activeSummary.content_1} />
            ) : (
              <UnavailableContentInsight label="Content 1" />
            )}
            {activeSummary.content_2 ? (
              <InsightScoreCard content={activeSummary.content_2} />
            ) : (
              <UnavailableContentInsight label="Content 2" />
            )}
          </div>

          <HookComparisonCard
            content1={activeSummary.content_1 ?? null}
            content2={activeSummary.content_2 ?? null}
            comparison={activeSummary.comparison}
          />

          <RecommendationList
            recommendations={activeSummary.comparison.top_recommendations}
            exampleRewrite={
              activeSummary.comparison.example_rewrite_for_content_2
            }
          />

          {activeSummary.notes.length > 0 ? (
            <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                Notes
              </p>
              <ul className="mt-2 grid gap-2">
                {activeSummary.notes.map((note) => (
                  <li key={note} className="text-sm leading-6 text-slate-600">
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function OverallComparisonCard({
  comparison,
}: {
  comparison: ComparisonInsight;
}) {
  return (
    <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
        Confirmed Public Metrics
      </p>
      <h3 className="mt-2 text-base font-semibold text-slate-950">
        Overall comparison
      </h3>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <Metric
          label="Confirmed metric winner"
          value={comparison.confirmed_metric_winner}
        />
        <Metric label="Hook winner" value={comparison.hook_winner} />
        <Metric
          label="Overall insight winner"
          value={comparison.overall_insight_winner}
        />
      </dl>

      <p className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-700">
        {comparison.main_reason}
      </p>
      <p className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-600">
        <span className="font-medium text-slate-700">Metadata Confidence: </span>
        {comparison.confidence_note}
      </p>
    </section>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  return (
    <div>
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-950">
        {value || "Unavailable"}
      </dd>
    </div>
  );
}

function UnavailableContentInsight({ label }: { label: "Content 1" | "Content 2" }) {
  return (
    <article className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
        {label}
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        Creator Insight Score unavailable for this content item.
      </p>
    </article>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not load Creator Insight Summary.";
}
