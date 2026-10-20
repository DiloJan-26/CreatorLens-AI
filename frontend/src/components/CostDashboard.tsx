"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getCostMetrics } from "@/lib/api";
import {
  getActiveProjectId,
  subscribeToActiveProject,
} from "@/lib/app-session";
import type {
  CostMetricsResponse,
  LlmRunSummary,
  NumericValue,
} from "@/types/cost";

export function CostDashboard() {
  const [projectId, setProjectId] = useState<string | null>(() =>
    getActiveProjectId(),
  );
  const [metrics, setMetrics] = useState<CostMetricsResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await getCostMetrics(projectId);
      setMetrics(response);
      setSelectedRunId((current) =>
        response.runs.some((run) => run.id === current)
          ? current
          : response.runs[0]?.id ?? null,
      );
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(
    () =>
      subscribeToActiveProject((nextProjectId) => {
        setProjectId(nextProjectId);
        setMetrics(null);
        setSelectedRunId(null);
      }),
    [],
  );

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      void loadMetrics();
    }, 0);

    return () => window.clearTimeout(loadTimer);
  }, [loadMetrics]);

  const selectedRun = useMemo(
    () =>
      metrics?.runs.find((run) => run.id === selectedRunId) ??
      metrics?.runs[0] ??
      null,
    [metrics, selectedRunId],
  );

  const averages = useMemo(
    () => ({
      retrieval: averageKnown(metrics?.runs, "retrieval_latency_ms"),
      llm: averageKnown(metrics?.runs, "llm_latency_ms"),
    }),
    [metrics],
  );

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-10 text-slate-950 dark:bg-slate-950 dark:text-slate-50 sm:px-8 lg:px-10">
      <div className="mx-auto max-w-7xl space-y-8">
        <header className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="grid gap-8 p-7 sm:p-9 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="max-w-3xl">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700 dark:text-teal-300">
                LLM operations
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Cost and latency dashboard
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-600 dark:text-slate-300 sm:text-base">
                Inspect persisted token usage, model and prompt versions,
                retrieval balance, latency, trace coverage, and available cost
                estimates from the deployed observability service.
              </p>
            </div>
            <div className="flex flex-col items-start gap-3 lg:items-end">
              <CoverageBadge run={metrics?.runs[0] ?? null} />
              <button
                type="button"
                onClick={() => void loadMetrics()}
                disabled={isLoading}
                className="inline-flex h-10 items-center justify-center rounded-full border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:text-white"
              >
                {isLoading ? "Refreshing..." : "Refresh telemetry"}
              </button>
            </div>
          </div>
          <div className="flex flex-col gap-2 border-t border-slate-200 bg-slate-50 px-7 py-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-300 sm:flex-row sm:items-center sm:justify-between">
            <span>Read-only operational view. No model calls are triggered here.</span>
            <span className="font-mono text-xs">
              {projectId ? `Active project ${shortId(projectId)}` : "All projects"}
            </span>
          </div>
        </header>

        {error ? <ErrorBanner message={error} onRetry={loadMetrics} /> : null}

        {isLoading && !metrics ? (
          <DashboardSkeleton />
        ) : metrics ? (
          <>
            <SummaryCards metrics={metrics} averages={averages} />
            <UsagePanel metrics={metrics} averages={averages} />
            <section className="grid gap-8 xl:grid-cols-[0.9fr_1.4fr]">
              <RunHistory
                runs={metrics.runs}
                selectedRunId={selectedRun?.id ?? null}
                onSelect={setSelectedRunId}
              />
              <RunInspection run={selectedRun} />
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}

function SummaryCards({
  metrics,
  averages,
}: {
  metrics: CostMetricsResponse;
  averages: { retrieval: number | null; llm: number | null };
}) {
  const cards = [
    {
      label: "Tracked generations",
      value: formatInteger(metrics.totals.event_count),
      note: `${metrics.runs.length} recent runs visible`,
    },
    {
      label: "Total tokens",
      value: formatInteger(metrics.totals.total_tokens),
      note: `${formatInteger(metrics.totals.input_tokens)} in · ${formatInteger(metrics.totals.output_tokens)} out`,
    },
    {
      label: "Estimated cost",
      value: formatCost(metrics.totals.estimated_cost_usd),
      note:
        metrics.totals.estimated_cost_usd === null
          ? "Pricing is not configured"
          : "Configured model-rate estimate",
    },
    {
      label: "Average latency",
      value:
        averages.llm === null
          ? "Unavailable"
          : formatDuration(averages.llm + (averages.retrieval ?? 0)),
      note: `${formatDuration(averages.retrieval)} retrieval · ${formatDuration(averages.llm)} LLM`,
    },
  ];

  return (
    <section
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
      aria-label="LLM operations summary"
    >
      {cards.map((card) => (
        <article
          key={card.label}
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            {card.label}
          </p>
          <p className="mt-3 text-2xl font-semibold tracking-tight">
            {card.value}
          </p>
          <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
            {card.note}
          </p>
        </article>
      ))}
    </section>
  );
}

function UsagePanel({
  metrics,
  averages,
}: {
  metrics: CostMetricsResponse;
  averages: { retrieval: number | null; llm: number | null };
}) {
  const totalTokens = metrics.totals.total_tokens;
  const inputShare =
    totalTokens > 0 ? metrics.totals.input_tokens / totalTokens : null;
  const outputShare =
    totalTokens > 0 ? metrics.totals.output_tokens / totalTokens : null;
  const totalLatency = (averages.retrieval ?? 0) + (averages.llm ?? 0);
  const retrievalShare =
    totalLatency > 0 && averages.retrieval !== null
      ? averages.retrieval / totalLatency
      : null;
  const llmShare =
    totalLatency > 0 && averages.llm !== null
      ? averages.llm / totalLatency
      : null;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-7">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
            Usage signals
          </p>
          <h2 className="mt-2 text-xl font-semibold">Token and latency mix</h2>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Based on available persisted observations
        </p>
      </div>
      <div className="mt-6 grid gap-8 md:grid-cols-2">
        <div>
          <SignalBar
            label="Input tokens"
            value={formatInteger(metrics.totals.input_tokens)}
            share={inputShare}
          />
          <SignalBar
            label="Output tokens"
            value={formatInteger(metrics.totals.output_tokens)}
            share={outputShare}
          />
        </div>
        <div>
          <SignalBar
            label="Average retrieval"
            value={formatDuration(averages.retrieval)}
            share={retrievalShare}
          />
          <SignalBar
            label="Average LLM generation"
            value={formatDuration(averages.llm)}
            share={llmShare}
          />
        </div>
      </div>
    </section>
  );
}

function SignalBar({
  label,
  value,
  share,
}: {
  label: string;
  value: string;
  share: number | null;
}) {
  const bounded = share === null ? 0 : Math.min(Math.max(share, 0), 1);

  return (
    <div className="mb-5 last:mb-0">
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-slate-700 dark:text-slate-200">
          {label}
        </span>
        <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
          {value}
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
  runs: LlmRunSummary[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
        History
      </p>
      <h2 className="mt-2 text-xl font-semibold">Recent LLM runs</h2>
      <div className="mt-5 max-h-[760px] space-y-3 overflow-y-auto pr-1">
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
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">
                    {friendlyPrompt(run.prompt_name)}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">
                    {run.llm_model}
                  </p>
                </div>
                <RunState run={run} />
              </div>
              <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
                <span>{formatDate(run.completed_at ?? run.created_at)}</span>
                <span>
                  {run.total_tokens === null
                    ? "Tokens unavailable"
                    : `${formatInteger(run.total_tokens)} tokens`}
                </span>
              </div>
            </button>
          );
        })}
        {runs.length === 0 ? (
          <EmptyState text="No LLM runs are available for this scope." />
        ) : null}
      </div>
    </section>
  );
}

function RunInspection({ run }: { run: LlmRunSummary | null }) {
  if (!run) {
    return (
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
          Inspection
        </p>
        <h2 className="mt-2 text-xl font-semibold">Run telemetry</h2>
        <div className="mt-5">
          <EmptyState text="Select a run to inspect its telemetry." />
        </div>
      </section>
    );
  }

  const sourceEntries = Object.entries(run.source_balance).filter(
    ([, value]) => typeof value === "number",
  ) as [string, number][];

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">
            Inspection
          </p>
          <h2 className="mt-2 text-xl font-semibold">Run telemetry</h2>
        </div>
        <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
          {shortId(run.id)}
        </span>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <TelemetryValue label="Provider" value={run.llm_provider} />
        <TelemetryValue label="Model" value={run.llm_model} />
        <TelemetryValue
          label="Prompt"
          value={
            run.prompt_name
              ? `${run.prompt_name} · v${run.prompt_version ?? "Unavailable"}`
              : "Unavailable"
          }
        />
        <TelemetryValue
          label="Input tokens"
          value={formatNullableInteger(run.input_tokens)}
        />
        <TelemetryValue
          label="Output tokens"
          value={formatNullableInteger(run.output_tokens)}
        />
        <TelemetryValue
          label="Total tokens"
          value={formatNullableInteger(run.total_tokens)}
        />
        <TelemetryValue
          label="Retrieval latency"
          value={formatDuration(run.retrieval_latency_ms)}
        />
        <TelemetryValue
          label="LLM latency"
          value={formatDuration(run.llm_latency_ms)}
        />
        <TelemetryValue
          label="Retrieved chunks"
          value={formatNullableInteger(run.retrieved_chunk_count)}
        />
      </div>

      <div className="mt-7 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            Retrieval balance
          </h3>
          <div className="mt-3 space-y-2">
            {sourceEntries.map(([source, count]) => (
              <div
                key={source}
                className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm dark:border-slate-800 dark:bg-slate-950/60"
              >
                <span>{friendlyLabel(source)}</span>
                <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                  {count} chunks
                </span>
              </div>
            ))}
            {sourceEntries.length === 0 ? (
              <EmptyState text="Source balance is unavailable." compact />
            ) : null}
          </div>
        </div>

        <div>
          <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
            Reliability signals
          </h3>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <SignalPill label="LangSmith trace" value={Boolean(run.langsmith_trace_id)} />
            <SignalPill label="Cache hit" value={run.cache_hit} />
            <SignalPill label="Cache miss" value={run.cache_miss} />
            <SignalPill label="Embedding reused" value={run.embedding_reused} />
            <SignalPill
              label="Transcript fallback"
              value={run.transcript_fallback_used}
            />
            <SignalPill
              label="Error"
              value={run.error_code ? true : false}
              trueLabel={run.error_code ?? "Recorded"}
              falseLabel="None"
              invert
            />
          </div>
        </div>
      </div>

      <div className="mt-7 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60">
        <div className="grid gap-4 sm:grid-cols-2">
          <TelemetryValue
            label="Transcript provider"
            value={run.transcript_provider ?? "Unavailable"}
            plain
          />
          <TelemetryValue
            label="LangSmith trace ID"
            value={run.langsmith_trace_id ?? "Unavailable"}
            plain
            mono
          />
          <TelemetryValue
            label="Session ID"
            value={run.session_id ?? "Unavailable"}
            plain
            mono
          />
          <TelemetryValue
            label="Retrieval run ID"
            value={run.retrieval_run_id ?? "Unavailable"}
            plain
            mono
          />
        </div>
      </div>
    </section>
  );
}

function TelemetryValue({
  label,
  value,
  plain = false,
  mono = false,
}: {
  label: string;
  value: string;
  plain?: boolean;
  mono?: boolean;
}) {
  return (
    <div
      className={
        plain
          ? "min-w-0"
          : "min-w-0 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/60"
      }
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p
        className={`mt-2 break-words text-sm font-semibold ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function SignalPill({
  label,
  value,
  trueLabel = "Yes",
  falseLabel = "No",
  invert = false,
}: {
  label: string;
  value: boolean | null;
  trueLabel?: string;
  falseLabel?: string;
  invert?: boolean;
}) {
  const state = value === null ? "unknown" : value ? "true" : "false";
  const positive = invert ? state === "false" : state === "true";
  const labelValue =
    state === "unknown" ? "Unavailable" : value ? trueLabel : falseLabel;

  return (
    <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs dark:border-slate-800 dark:bg-slate-950/60">
      <span className="text-slate-600 dark:text-slate-300">{label}</span>
      <span
        className={`font-semibold ${
          state === "unknown"
            ? "text-slate-500"
            : positive
              ? "text-emerald-600 dark:text-emerald-300"
              : "text-amber-600 dark:text-amber-300"
        }`}
      >
        {labelValue}
      </span>
    </div>
  );
}

function CoverageBadge({ run }: { run: LlmRunSummary | null }) {
  const covered = Boolean(
    run &&
      run.status === "COMPLETED" &&
      run.prompt_version &&
      run.langsmith_trace_id,
  );

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold ${
        covered
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
          : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          covered ? "bg-emerald-500" : "bg-amber-500"
        }`}
      />
      {run
        ? covered
          ? "Observability active"
          : "Coverage incomplete"
        : "No runs available"}
    </span>
  );
}

function RunState({ run }: { run: LlmRunSummary }) {
  const completed = run.status === "COMPLETED" && !run.error_code;

  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
        completed
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
          : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-200"
      }`}
    >
      {run.status}
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
    <div
      role="alert"
      className="flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-200 sm:flex-row sm:items-center sm:justify-between"
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={() => void onRetry()}
        className="font-semibold underline underline-offset-4"
      >
        Try again
      </button>
    </div>
  );
}

function EmptyState({ text, compact = false }: { text: string; compact?: boolean }) {
  return (
    <div
      className={`rounded-2xl border border-dashed border-slate-300 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400 ${
        compact ? "px-4 py-5" : "px-5 py-10"
      }`}
    >
      {text}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8" aria-label="Loading LLM operations dashboard">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={index}
            className="h-32 animate-pulse rounded-2xl bg-slate-200 dark:bg-slate-800"
          />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-3xl bg-slate-200 dark:bg-slate-800" />
    </div>
  );
}

function averageKnown(
  runs: LlmRunSummary[] | undefined,
  key: "retrieval_latency_ms" | "llm_latency_ms",
): number | null {
  const values = (runs ?? [])
    .map((run) => run[key])
    .filter((value): value is number => typeof value === "number");

  if (values.length === 0) {
    return null;
  }

  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function formatCost(value: NumericValue | null): string {
  if (value === null) {
    return "Unavailable";
  }

  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return "Unavailable";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: parsed < 0.01 ? 4 : 2,
    maximumFractionDigits: 6,
  }).format(parsed);
}

function formatDuration(value: number | null): string {
  if (value === null) {
    return "Unavailable";
  }

  if (value < 1000) {
    return `${Math.round(value)} ms`;
  }

  return `${(value / 1000).toFixed(2)} s`;
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatNullableInteger(value: number | null): string {
  return value === null ? "Unavailable" : formatInteger(value);
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Unavailable"
    : new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function friendlyPrompt(value: string | null): string {
  return value ? friendlyLabel(value) : "Unversioned prompt";
}

function friendlyLabel(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part[0]?.toUpperCase() + part.slice(1))
    .join(" ");
}

function shortId(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value;
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "Could not load cost and latency telemetry.";
}
