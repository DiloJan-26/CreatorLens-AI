"use client";

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
  const [datasets, setDatasets] = useState<EvaluationDatasetSummary[]>([]);
  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<EvaluationRunDetail | null>(null);
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
      setSelectedRunId((current) => current ?? runResponse[0]?.id ?? null);
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
  }, [selectedRunId]);

  const latestRun = runs[0] ?? null;
  const accepted = latestRun ? isAcceptedRun(latestRun) : false;

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-950 dark:bg-slate-950 dark:text-slate-50 sm:px-8 lg:px-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <header className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="grid gap-8 p-7 sm:p-9 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">
                RAG quality
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Evaluation dashboard
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300 sm:text-base">
                Inspect deterministic retrieval and answer-quality regressions,
                evidence compliance, and case-level rubric results from the
                deployed evaluation service.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 lg:items-end">
              <StatusBadge accepted={accepted} run={latestRun} />
              <button
                type="button"
                onClick={() => void loadOverview()}
                disabled={isLoading}
                className="inline-flex h-10 items-center justify-center rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:text-white"
              >
                {isLoading ? "Refreshing..." : "Refresh results"}
              </button>
            </div>
          </div>
          <div className="border-t border-slate-200 bg-slate-50 px-7 py-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-300">
            Read-only quality view. Evaluation runs remain controlled through
            the backend acceptance workflow.
          </div>
        </header>

        {error ? <ErrorBanner message={error} onRetry={loadOverview} /> : null}

        {isLoading && runs.length === 0 ? (
          <DashboardSkeleton />
        ) : (
          <>
            <DatasetStrip datasets={datasets} />
            <OverviewCards run={latestRun} />
            <MetricPanel run={latestRun} />
            <section className="grid gap-8 xl:grid-cols-[0.85fr_1.45fr]">
              <RunHistory
                runs={runs}
                selectedRunId={selectedRunId}
                onSelect={setSelectedRunId}
              />
              <CaseResults detail={selectedRun} loading={isDetailLoading} />
            </section>
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
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
            Regression assets
          </p>
          <h2 id="datasets-title" className="mt-2 text-xl font-semibold">
            Deployed datasets
          </h2>
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {datasets.length} available
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {datasets.map((dataset) => (
          <article
            key={`${dataset.name}-${dataset.version}`}
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="font-semibold text-slate-950 dark:text-white">
                {friendlyDatasetName(dataset.name)}
              </h3>
              <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800 dark:bg-teal-950 dark:text-teal-200">
                v{dataset.version}
              </span>
            </div>
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
              {dataset.case_count} curated cases
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {dataset.answer_types.map((answerType) => (
                <span
                  key={answerType}
                  className="rounded-full border border-slate-200 px-2.5 py-1 text-xs capitalize text-slate-600 dark:border-slate-700 dark:text-slate-300"
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
      note: run?.failed_cases ? `${run.failed_cases} require review` : "No failed cases",
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
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Latest evaluation summary">
      {cards.map((card) => (
        <article
          key={card.label}
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            {card.label}
          </p>
          <p className="mt-3 text-2xl font-semibold tracking-tight">{card.value}</p>
          <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
            {card.note}
          </p>
        </article>
      ))}
    </section>
  );
}

function MetricPanel({ run }: { run: EvaluationRunSummary | null }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-7">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
            Latest run
          </p>
          <h2 className="mt-2 text-xl font-semibold">Quality signals</h2>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          {run ? formatDate(run.completed_at ?? run.created_at) : "No run available"}
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
        <span className="font-medium text-slate-700 dark:text-slate-200">{label}</span>
        <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
          {value === null ? "N/A" : value.toFixed(3)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
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
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
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
              className={`w-full rounded-2xl border p-4 text-left transition ${
                active
                  ? "border-teal-400 bg-teal-50 dark:border-teal-700 dark:bg-teal-950/50"
                  : "border-slate-200 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:hover:border-slate-700 dark:hover:bg-slate-950"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">
                    {friendlyDatasetName(run.dataset_name)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {formatDate(run.completed_at ?? run.created_at)}
                  </p>
                </div>
                <RunState run={run} />
              </div>
              <div className="mt-4 flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
                <span>v{run.dataset_version}</span>
                <span>{run.passed_cases}/{run.total_cases} passed</span>
              </div>
            </button>
          );
        })}
        {runs.length === 0 ? <EmptyState text="No persisted runs are available." /> : null}
      </div>
    </section>
  );
}

function CaseResults({ detail, loading }: { detail: EvaluationRunDetail | null; loading: boolean }) {
  const grouped = useMemo(() => {
    if (!detail) return [];
    return [...detail.results].sort((left, right) => {
      if (left.status === right.status) return left.case_id.localeCompare(right.case_id);
      return left.status === "FAILED" ? -1 : 1;
    });
  }, [detail]);

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
            Inspection
          </p>
          <h2 className="mt-2 text-xl font-semibold">Case-level results</h2>
        </div>
        {detail ? (
          <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
            {shortId(detail.run.id)}
          </span>
        ) : null}
      </div>
      <div className="mt-5 max-h-[900px] space-y-3 overflow-y-auto pr-1">
        {loading ? <EmptyState text="Loading case details..." /> : null}
        {!loading && grouped.map((result) => (
          <CaseResult key={result.case_id} result={result} />
        ))}
        {!loading && !detail ? <EmptyState text="Select a run to inspect its cases." /> : null}
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
    <details className="group rounded-2xl border border-slate-200 bg-slate-50 open:bg-white dark:border-slate-800 dark:bg-slate-950/60 dark:open:bg-slate-950">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">{friendlyCaseName(result.case_id)}</p>
          <p className="mt-1 text-xs capitalize text-slate-500 dark:text-slate-400">
            {result.answer_type ?? "Unknown answer type"} · {result.duration_ms ?? 0} ms
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {failedChecks > 0 ? (
            <span className="rounded-full bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-700 dark:bg-rose-950 dark:text-rose-200">
              {failedChecks} failed
            </span>
          ) : null}
          <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${result.status === "PASSED" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200" : "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-200"}`}>
            {result.status}
          </span>
        </div>
      </summary>
      <div className="border-t border-slate-200 p-4 dark:border-slate-800">
        <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Quality gates
        </h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {checks.map(([name, check]) => (
            <CheckRow key={name} name={name} check={check} />
          ))}
        </div>
        <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Scores
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {Object.entries(result.metric_scores).map(([name, value]) => (
            <span key={name} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
              {friendlyMetricName(name)}: {formatMetric(value)}
            </span>
          ))}
        </div>
        <h3 className="mt-5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Citations
        </h3>
        <div className="mt-3 flex flex-wrap gap-2">
          {result.citation_labels.map((label) => (
            <span key={label} className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-700 dark:bg-sky-950 dark:text-sky-200">
              {normalizeCitation(label)}
            </span>
          ))}
          {result.citation_labels.length === 0 ? (
            <span className="text-xs text-slate-500">No citations recorded.</span>
          ) : null}
        </div>
      </div>
    </details>
  );
}

function CheckRow({ name, check }: { name: string; check: EvaluationCheckResult }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">
          {friendlyMetricName(name)}
        </span>
        <span className={check.passed ? "text-emerald-600" : "text-rose-600"} aria-label={check.passed ? "Passed" : "Failed"}>
          {check.passed ? "✓" : "×"}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
        {check.message}
      </p>
    </div>
  );
}

function StatusBadge({ accepted, run }: { accepted: boolean; run: EvaluationRunSummary | null }) {
  return (
    <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${accepted ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"}`}>
      <span className={`h-2 w-2 rounded-full ${accepted ? "bg-emerald-500" : "bg-amber-500"}`} />
      {run ? (accepted ? "Quality gate passed" : "Review required") : "No run available"}
    </span>
  );
}

function RunState({ run }: { run: EvaluationRunSummary }) {
  const passed = isAcceptedRun(run);
  return (
    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${passed ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200" : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200"}`}>
      {run.status === "COMPLETED" ? (passed ? "Passed" : "Review") : run.status}
    </span>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => Promise<void> }) {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100 sm:flex-row sm:items-center sm:justify-between">
      <p>{message}</p>
      <button type="button" onClick={() => void onRetry()} className="font-semibold underline underline-offset-4">
        Retry
      </button>
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Loading evaluation dashboard">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900" />
      ))}
    </section>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
      {text}
    </div>
  );
}

function isAcceptedRun(run: EvaluationRunSummary): boolean {
  return run.status === "COMPLETED" && run.failed_cases === 0 && metricValue(run.aggregate_metrics, "pass_rate") === 1;
}

function metricValue(metrics: Record<string, unknown> | undefined, key: string): number | null {
  const value = metrics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatMetric(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : "N/A";
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Unknown time"
    : new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" }).format(date);
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
  return value.replace(/_ragas$|_lexical$/g, "").split("_").map(capitalize).join(" ");
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
