"use client";

import { useCallback, useEffect, useState } from "react";

import { getCreatorInsightSummary } from "@/lib/api";
import type {
  ComparisonInsight,
  ContentInsight,
  CreatorInsightSummaryResponse,
} from "@/types/project";

import { HookComparisonCard } from "./HookComparisonCard";
import { InsightScoreCard } from "./InsightScoreCard";
import { RecommendationList } from "./RecommendationList";
import { CreatorRecommendationList } from "./CreatorRecommendationList";
import { Icon } from "./ui";

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
  const [summary, setSummary] = useState<CreatorInsightSummaryResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const visibleSummary = initialSummary ?? summary;
  const activeSummary =
    projectId && visibleSummary?.project_id === projectId
      ? visibleSummary
      : null;

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
    <section className="workspace-panel rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Creator intelligence
          </p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950 flex items-center gap-2">
            <Icon name="target" size={21} /> Creator Insight Summary
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            CreatorLens AI separates confirmed public performance, creator-size
            efficiency, and creative structure so the comparison does not
            mistake data availability for content strength.
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

      <details className="insight-method mt-4 text-sm text-slate-600">
        <summary>How scores are calculated</summary>
        <p className="py-2 leading-6">
          Creator Insight Score is a deterministic review signal combining
          eligible public performance, creator efficiency and validated semantic
          creative structure. Evidence confidence is reported separately. Metadata Availability is informational and is not a
          creative strength or performance score.
          {!indexReady
            ? " Vector search is not required for this summary."
            : ""}
        </p>
      </details>

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {!projectId ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Creator Insight Summary appears after Content 1 and Content 2 are
          analyzed.
        </p>
      ) : null}

      {isLoading && !activeSummary ? (
        <p className="mt-4 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Loading Creator Insight Summary...
        </p>
      ) : null}

      {activeSummary ? (
        <div className="mt-5 grid gap-4">
          {activeSummary.creator_recommendations ? (
            <>
              <CreatorRecommendationList bundle={activeSummary.creator_recommendations} contents={[activeSummary.content_1, activeSummary.content_2]} />
              <details className="detail-disclosure">
                <summary>Legacy recommendations / legacy-1.0.0</summary>
                <RecommendationList recommendations={activeSummary.comparison.top_recommendations} exampleRewrite={activeSummary.comparison.example_rewrite_for_content_2} />
              </details>
            </>
          ) : (
            <div>
              <p className="text-sm text-slate-600">Legacy recommendations / legacy-1.0.0</p>
              <RecommendationList recommendations={activeSummary.comparison.top_recommendations} exampleRewrite={activeSummary.comparison.example_rewrite_for_content_2} />
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            {[activeSummary.content_1, activeSummary.content_2].map((content) =>
              content?.scoring ? <EvidenceScoring key={content.slot} content={content} /> : null,
            )}
          </div>
          <p className="text-sm text-slate-600">The comparison panels below retain legacy-1.0.0. Evidence-grounded recommendations above have their own policy label. The versioned evidence-aware scores above do not select a winner.</p>
          <details className="detail-disclosure"><summary>Legacy scores / legacy-1.0.0</summary><ScoreComparison summary={activeSummary} /></details>
          <details className="detail-disclosure">
            <summary>Legacy comparison rationale / legacy-1.0.0</summary>
            <OverallComparisonCard comparison={activeSummary.comparison} />
          </details>

          <details className="detail-disclosure">
            <summary>Legacy per-content scores & evidence gaps / legacy-1.0.0</summary>
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
          </details>

          <details className="detail-disclosure"><summary>Legacy verbal-hook analysis / legacy-1.0.0</summary><HookComparisonCard
            content1={activeSummary.content_1 ?? null}
            content2={activeSummary.content_2 ?? null}
            comparison={activeSummary.comparison}
          /></details>

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
        Trustworthy Comparison
      </p>
      <h3 className="mt-2 text-base font-semibold text-slate-950">
        Overall comparison
      </h3>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Performance winner"
          value={comparison.confirmed_metric_winner}
        />
        <Metric
          label="Creator efficiency winner"
          value={comparison.creator_efficiency_winner}
        />
        <Metric
          label="Creative structure winner"
          value={comparison.creative_structure_winner}
        />
        <Metric
          label="Overall signal winner"
          value={comparison.overall_insight_winner}
        />
      </dl>

      <p className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-700">
        {comparison.main_reason}
      </p>
      <p className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-600">
        <span className="font-medium text-slate-700">
          Evidence confidence:{" "}
        </span>
        {comparison.confidence_note}
      </p>
    </section>
  );
}

function Metric({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-950">
        {value || "Unavailable"}
      </dd>
    </div>
  );
}

function UnavailableContentInsight({
  label,
}: {
  label: "Content 1" | "Content 2";
}) {
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

function ScoreComparison({
  summary,
}: {
  summary: CreatorInsightSummaryResponse;
}) {
  const c = [summary.content_1, summary.content_2];
  const rows = [
    "Hook clarity",
    "Creative structure",
    "Public performance",
    "Creator efficiency",
    "Overall insight",
  ];
  const vals = c.map((v) =>
    v
      ? [
          v.scores.hook_clarity,
          v.scores.creative_structure_score,
          v.scores.public_performance_score,
          v.scores.creator_efficiency_score,
          v.scores.overall_score,
        ]
      : [],
  );
  return (
    <div className="score-comparison">
      <h3 className="text-lg mb-2">Side-by-side assessment</h3>
      <p className="muted text-xs mb-4">
        Deterministic heuristic scores out of 10. These are review signals, not
        measured retention or causal performance estimates.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Signal</th>
              <th scope="col">Content 1</th>
              <th scope="col">Content 2</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((label, i) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                {vals.map((v, j) => (
                  <td key={j}>
                    {v[i] == null ? (
                      "Unavailable"
                    ) : (
                      <>
                        <span className="font-semibold">
                          {v[i]}
                          <span className="muted text-xs"> / 10</span>
                        </span>
                        <div className="score-track" aria-hidden="true">
                          <span
                            style={{
                              width: `${Math.max(0, Math.min(10, v[i])) * 10}%`,
                            }}
                          />
                        </div>
                      </>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EvidenceScoring({ content }: { content: ContentInsight }) {
  const scoring = content.scoring;
  if (!scoring) return null;
  const fields = ["reach", "engagement", "public_performance", "creator_efficiency", "creative_structure", "overall"] as const;
  return <section className="rounded-lg border border-slate-200 p-4" aria-label={`${content.label} evidence-aware scores`}>
    <h3 className="font-semibold">{content.label} / Evidence-aware scoring</h3>
    <p className="text-sm muted">{scoring.policy.version} / Uncalibrated heuristics</p>
    <dl className="mt-3 grid gap-3">{fields.map(field => {
      const semantic = field === "creative_structure" || field === "overall";
      const value = semantic ? content.semantic_scoring?.[field] : scoring[field];
      return <div key={field}>
        <dt className="font-medium capitalize">{field === "creative_structure" ? "Semantic creative score" : field.replaceAll("_", " ")}</dt>
        <dd>{value?.score == null ? "Not assessable" : `${value.score.toFixed(2)} / 10`}{value ? ` / Coverage ${(value.coverage * 100).toFixed(0)}%` : " / Compatible semantic evidence required"}</dd>
        {value && <><dd className="text-sm muted">{value.rationale}{value.missing_inputs.length ? ` Missing: ${value.missing_inputs.join(", ")}.` : ""}</dd><dd><details className="text-sm mt-2"><summary>Score contributions and limitations</summary><ul>{value.components?.map((part, index) => <li key={`${part.feature}-${index}`} className="mt-2 break-words">{part.feature}: {part.contribution == null ? "Unavailable" : part.contribution.toFixed(3)} / {part.rule} / Source: {part.source}</li>)}</ul><p className="muted mt-2">{value.limitations?.join(" ")}</p></details></dd></>}
      </div>;
    })}</dl>
    {scoring.metrics && <details className="detail-disclosure mt-4"><summary>Normalized metric inputs and context</summary><dl className="mt-3 grid gap-2">{Object.entries(scoring.metrics.rates_percent).map(([name, value]) => <div key={name}><dt className="capitalize">{name.replaceAll("_", " ")}</dt><dd>{value == null ? "Unavailable" : `${value.toFixed(3)}%`}</dd></div>)}</dl><p className="mt-3 text-sm muted">Engagement eligibility: {scoring.metrics.engagement_status}. Views per current creator size: {scoring.metrics.views_per_current_creator_size ?? "Unavailable"}. Published: {scoring.metrics.publication_date ?? "Unavailable"}. Observed: {scoring.metrics.observed_at ?? "Unavailable"}. {scoring.metrics.limitations.join(" ")}</p></details>}
    {scoring.evidence && <p className="text-sm muted mt-4">Evidence assessment: {scoring.evidence.transcript_status} transcript / {scoring.evidence.source_reliability} source reliability / {(scoring.evidence.metric_completeness * 100).toFixed(0)}% metric completeness. {scoring.evidence.limitations.join(" ")} Evidence confidence is not a content-quality bonus.</p>}
  </section>;
}
