"use client";

import { PageHeading, Icon } from "./ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getEvaluationDatasets,
  getEvaluationRun,
  getEvaluationRuns,
} from "@/lib/api";
import type {
  EvaluationCheckResult,
  EvaluationDatasetSummary,
  EvaluationResultSummary,
  EvaluationRunDetail,
  EvaluationRunSummary,
} from "@/types/evaluation";

const QUALITY_METRICS = [
  "pass_rate",
  "faithfulness_lexical",
  "response_relevance_lexical",
  "context_relevance_lexical",
  "context_precision_ragas",
  "context_recall_ragas",
  "citation_presence",
  "missing_evidence_compliance",
] as const;

export function EvaluationDashboard() {
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [datasets, setDatasets] = useState<EvaluationDatasetSummary[]>([]);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<EvaluationRunDetail | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [datasetResponse, runResponse] = await Promise.all([
        getEvaluationDatasets(),
        getEvaluationRuns(),
      ]);
      setDatasets(datasetResponse);
      setRuns(runResponse);
      setSelectedRunId((current) =>
        runResponse.some((r) => r.id === current)
          ? current
          : (runResponse[0]?.id ?? null),
      );
      setRefreshVersion((v) => v + 1);
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      void loadOverview();
    }, 0);

    return () => window.clearTimeout(loadTimer);
  }, [loadOverview]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    let active = true;
    const loadTimer = window.setTimeout(() => {
      setIsDetailLoading(true);
      setSelectedRun(null);
      setError(null);
      getEvaluationRun(selectedRunId)
        .then((detail) => {
          if (active) {
            setSelectedRun(detail);
          }
        })
        .catch((loadError) => {
          if (active) {
            setError(errorMessage(loadError));
          }
        })
        .finally(() => {
          if (active) {
            setIsDetailLoading(false);
          }
        });
    }, 0);

    return () => {
      active = false;
      window.clearTimeout(loadTimer);
    };
  }, [selectedRunId, refreshVersion]);

  const latestRun = runs.find((r) => r.id === selectedRunId) ?? null;
  const accepted = latestRun ? isAcceptedRun(latestRun) : false;

  return (
    <main className="page-container engineering-view">
      <div className="mx-auto max-w-7xl space-y-8">
        <PageHeading
          eyebrow="Engineering / Read-only"
          title="RAG Evaluation"
          icon="shield"
          description="Inspect regression quality, source coverage and evidence compliance."
          action={
            <button
              className="button-secondary"
              onClick={() => void loadOverview()}
              disabled={isLoading}
            >
              <Icon name="refresh" size={15} />
              {isLoading ? "Refreshing..." : "Refresh results"}
            </button>
          }
        />
        <div className="engineering-meta flex flex-wrap items-center justify-between gap-3">
          <p className="muted text-sm">
            Selected run /{" "}
            {latestRun
              ? friendlyDatasetName(latestRun.dataset_name)
              : "No persisted run"}
          </p>
          {isLoading ? (
            <span role="status" className="muted text-sm">
              Loading observations...
            </span>
          ) : error ? (
            <span className="muted text-sm">Refresh incomplete</span>
          ) : (
            <StatusBadge accepted={accepted} run={latestRun} />
          )}
        </div>
        <details className="notice text-sm">
          <summary>How to read these results</summary>
          <p className="muted">
            Pass rate reflects deterministic rubric gates. Lexical faithfulness
            and relevance measure text-based signals, not LLM-judge assessments.
            Context precision and recall use the configured RAGAS metrics.
            Passing a regression suite does not guarantee every live answer is
            correct. This view cannot execute evaluations.
          </p>
        </details>
        {error ? <ErrorBanner message={error} onRetry={loadOverview} /> : null}

        {isLoading && runs.length === 0 ? (
          <DashboardSkeleton />
        ) : error && runs.length === 0 ? null : (
          <>
            {error && (
              <p className="notice">
                Showing previously loaded observations. They may be out of date.
              </p>
            )}
            <OverviewCards run={latestRun} />
            <div className="engineering-grid">
              <MetricPanel run={latestRun} />
              <RunHistory
                runs={runs}
                selectedRunId={selectedRunId}
                onSelect={setSelectedRunId}
              />
            </div>
            <CaseResults
              detail={
                selectedRun?.run.id === selectedRunId ? selectedRun : null
              }
              loading={isDetailLoading}
            />
            <details className="dataset-disclosure">
              <summary>
                Evaluation datasets & versions ({datasets.length})
              </summary>
              <DatasetStrip datasets={datasets} />
            </details>
          </>
        )}
      </div>
    </main>
  );
}

function DatasetStrip({ datasets }: { datasets: EvaluationDatasetSummary[] }) {
  return (
    <section aria-labelledby="datasets-title">
      <div className="mb-4 flex items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
            Regression assets
          </p>
          <h2 id="datasets-title" className="mt-2 text-xl font-semibold">
            Deployed datasets
          </h2>
        </div>
        <p className="text-sm text-slate-500">{datasets.length} available</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {datasets.map((dataset) => (
          <article
            key={`${dataset.name}-${dataset.version}`}
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="font-semibold text-slate-950">
                {friendlyDatasetName(dataset.name)}
              </h3>
              <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800">
                v{dataset.version}
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-600">
              {dataset.case_count} curated cases
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {dataset.answer_types.map((answerType) => (
                <span
                  key={answerType}
                  className="rounded-full border border-slate-200 px-2.5 py-1 text-xs capitalize text-slate-600"
                >
                  {answerType}
                </span>
              ))}
            </div>
          </article>
        ))}
        {datasets.length === 0 ? (
          <EmptyState text="No evaluation datasets were returned." />
        ) : null}
      </div>
    </section>
  );
}

function OverviewCards({ run }: { run: EvaluationRunSummary | null }) {
  const passRate = metricValue(run?.aggregate_metrics, "pass_rate");
  const cards = [
    {
      label: "Pass rate",
      value: passRate === null ? "Unavailable" : formatPercent(passRate),
      note: "Hardened quality gates",
    },
    {
      label: "Cases passed",
      value: run ? `${run.passed_cases}/${run.total_cases}` : "Unavailable",
      note: !run
        ? "No persisted run"
        : run.failed_cases
          ? `${run.failed_cases} require review`
          : "No failed cases",
    },
    {
      label: "Dataset",
      value: run ? `v${run.dataset_version}` : "Unavailable",
      note: run ? friendlyDatasetName(run.dataset_name) : "No persisted run",
    },
    {
      label: "Evaluator",
      value: run ? evaluatorVersion(run.evaluator) : "Unavailable",
      note: "RAGAS + DeepEval deterministic",
    },
  ];

  return (
    <section
      className="engineering-stats"
      aria-label="Selected evaluation summary"
    >
      {cards.map((card, index) => (
        <article key={card.label} className="engineering-stat">
          <span className="stat-icon">
            <Icon
              name={["shield", "check", "evidence", "target"][index]}
              size={21}
            />
          </span>
          <p className="stat-label">{card.label}</p>
          <p className="stat-value">{card.value}</p>
          <p className="stat-note">{card.note}</p>
        </article>
      ))}
    </section>
  );
}

function MetricPanel({ run }: { run: EvaluationRunSummary | null }) {
  return (
    <section className="quality-panel rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
            Selected run
          </p>
          <h2 className="mt-2 text-xl font-semibold">Quality signals</h2>
        </div>
        <p className="text-xs text-slate-500">
          {run
            ? formatDate(run.completed_at ?? run.created_at)
            : "No run available"}
        </p>
      </div>
      <div className="mt-6 grid gap-x-8 gap-y-5 md:grid-cols-2">
        {QUALITY_METRICS.map((metric) => (
          <MetricBar
            key={metric}
            label={friendlyMetricName(metric)}
            value={metricValue(run?.aggregate_metrics, metric)}
          />
        ))}
      </div>
    </section>
  );
}

function MetricBar({ label, value }: { label: string; value: number | null }) {
  const bounded = value === null ? 0 : Math.min(Math.max(value, 0), 1);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-mono text-xs text-slate-500">
          {value === null ? "N/A" : value.toFixed(3)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-teal-500"
          style={{ width: `${bounded * 100}%` }}
        />
      </div>
    </div>
  );
}

function RunHistory({
  runs,
  selectedRunId,
  onSelect,
}: {
  runs: EvaluationRunSummary[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
        History
      </p>
      <h2 className="mt-2 text-xl font-semibold">Persisted runs</h2>
      <div className="mt-5 space-y-3">
        {runs.map((run) => {
          const active = run.id === selectedRunId;
          return (
            <button
              type="button"
              key={run.id}
              onClick={() => onSelect(run.id)}
              aria-pressed={active}
              className={`w-full rounded-2xl border p-4 text-left transition ${
                active
                  ? "border-teal-400 bg-teal-50"
                  : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">
                    {friendlyDatasetName(run.dataset_name)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {formatDate(run.completed_at ?? run.created_at)}
                  </p>
                </div>
                <RunState run={run} />
              </div>
              <div className="mt-4 flex items-center justify-between text-xs text-slate-600">
                <span>v{run.dataset_version}</span>
                <span>
                  {run.passed_cases}/{run.total_cases} passed
                </span>
              </div>
            </button>
          );
        })}
        {runs.length === 0 ? (
          <EmptyState text="No persisted runs are available." />
        ) : null}
      </div>
    </section>
  );
}

function CaseResults({
  detail,
  loading,
}: {
  detail: EvaluationRunDetail | null;
  loading: boolean;
}) {
  const grouped = useMemo(() => {
    if (!detail) return [];
    return [...detail.results].sort((left, right) => {
      if (left.status === right.status)
        return left.case_id.localeCompare(right.case_id);
      return left.status === "FAILED" ? -1 : 1;
    });
  }, [detail]);

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
            Inspection
          </p>
          <h2 className="mt-2 text-xl font-semibold">Case-level results</h2>
        </div>
        {detail ? (
          <span className="font-mono text-[14px] text-slate-500">
            {shortId(detail.run.id)}
          </span>
        ) : null}
      </div>
      <div className="mt-5 max-h-[900px] space-y-3 overflow-y-auto pr-1">
        {loading ? <EmptyState text="Loading case details..." /> : null}
        {!loading &&
          grouped.map((result) => (
            <CaseResult key={result.case_id} result={result} />
          ))}
        {!loading && !detail ? (
          <EmptyState text="Select a run to inspect its cases." />
        ) : null}
        {!loading && detail && grouped.length === 0 ? (
          <EmptyState text="This run has no case-level results." />
        ) : null}
      </div>
    </section>
  );
}

function CaseResult({ result }: { result: EvaluationResultSummary }) {
  const checks = Object.entries(result.rubric_results);
  const failedChecks = checks.filter(([, check]) => !check.passed).length;
  return (
    <details className="group rounded-2xl border border-slate-200 bg-slate-50 open:bg-white">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">
            {friendlyCaseName(result.case_id)}
          </p>
          <p className="mt-1 text-xs capitalize text-slate-500">
            {result.answer_type ?? "Unknown answer type"} ·{" "}
            {result.duration_ms == null
              ? "Duration unavailable"
              : `${result.duration_ms} ms`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {failedChecks > 0 ? (
            <span className="rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700">
              {failedChecks} failed
            </span>
          ) : null}
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${result.status === "PASSED" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}
          >
            {result.status}
          </span>
        </div>
      </summary>
      <div className="border-t border-slate-200 p-4">
        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
          Quality gates
        </h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {checks.map(([name, check]) => (
            <CheckRow key={name} name={name} check={check} />
          ))}
        </div>
        <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
          Scores
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(result.metric_scores).map(([name, value]) => (
            <span
              key={name}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600"
            >
              {friendlyMetricName(name)}: {formatMetric(value)}
            </span>
          ))}
        </div>
        <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
          Citations
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {result.citation_labels.map((label) => (
            <span
              key={label}
              className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-700"
            >
              {normalizeCitation(label)}
            </span>
          ))}
          {result.citation_labels.length === 0 ? (
            <span className="text-xs text-slate-500">
              No citations recorded.
            </span>
          ) : null}
        </div>
      </div>
    </details>
  );
}

function CheckRow({
  name,
  check,
}: {
  name: string;
  check: EvaluationCheckResult;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-slate-700">
          {friendlyMetricName(name)}
        </span>
        <span
          className={check.passed ? "text-emerald-600" : "text-rose-600"}
          aria-label={check.passed ? "Passed" : "Failed"}
        >
          {check.passed ? "✓" : "×"}
        </span>
      </div>
      <p className="mt-2 text-[14px] leading-5 text-slate-500">
        {check.message}
      </p>
    </div>
  );
}

function StatusBadge({
  accepted,
  run,
}: {
  accepted: boolean;
  run: EvaluationRunSummary | null;
}) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${accepted ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}
    >
      <span
        className={`h-2 w-2 rounded-full ${accepted ? "bg-emerald-500" : "bg-amber-500"}`}
      />
      {run
        ? accepted
          ? "Quality gate passed"
          : "Review required"
        : "No run available"}
    </span>
  );
}

function RunState({ run }: { run: EvaluationRunSummary }) {
  const passed = isAcceptedRun(run);
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${passed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}
    >
      {run.status === "COMPLETED" ? (passed ? "Passed" : "Review") : run.status}
    </span>
  );
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => Promise<void>;
}) {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 sm:flex-row sm:items-center sm:justify-between">
      <p>{message}</p>
      <button
        type="button"
        onClick={() => void onRetry()}
        className="font-semibold underline underline-offset-4"
      >
        Retry
      </button>
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <section
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      aria-label="Loading evaluation dashboard"
    >
      {Array.from({ length: 4 }, (_, index) => (
        <div
          key={index}
          className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white"
        />
      ))}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-sm text-slate-500">
      {text}
    </div>
  );
}

function isAcceptedRun(run: EvaluationRunSummary): boolean {
  return (
    run.status === "COMPLETED" &&
    run.failed_cases === 0 &&
    metricValue(run.aggregate_metrics, "pass_rate") === 1
  );
}

function metricValue(
  metrics: Record<string, unknown> | undefined,
  key: string,
): number | null {
  const value = metrics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatMetric(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(3)
    : "N/A";
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Unknown time"
    : new Intl.DateTimeFormat("en", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function friendlyDatasetName(value: string): string {
  if (value === "creatorlens_core_v1") return "CreatorLens core";
  if (value === "creatorlens_ci_smoke_v1") return "CI smoke subset";
  return friendlyMetricName(value);
}

function friendlyCaseName(value: string): string {
  return value.replace(/_\d+$/, "").split("_").map(capitalize).join(" ");
}

function friendlyMetricName(value: string): string {
  const method = value.endsWith("_lexical")
    ? " / Lexical"
    : value.endsWith("_ragas")
      ? " / RAGAS"
      : "";
  return (
    value
      .replace(/_ragas$|_lexical$/g, "")
      .split("_")
      .map(capitalize)
      .join(" ") + method
  );
}

function capitalize(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}

function evaluatorVersion(value: string): string {
  const match = value.match(/v(\d+(?:\.\d+)*)$/);
  return match ? `v${match[1]}` : "Current";
}

function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function normalizeCitation(value: string): string {
  return value.replace(/Â·/g, "·");
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "Could not load evaluation results.";
}
