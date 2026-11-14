"use client";

import { useAccount } from "./AccountProvider";
import { PageHeading, Icon } from "./ui";
import { useCallback, useEffect, useMemo, useState, useRef } from "react";

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
  const {enabled,account}=useAccount();
  const [projectId, setProjectId] = useState<string | null>(null);
  const [scopeReady, setScopeReady] = useState(false);
  const requestVersion = useRef(0);
  const [metrics, setMetrics] = useState<CostMetricsResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMetrics = useCallback(async () => {
    const version = ++requestVersion.current;
    setIsLoading(true);
    setError(null);

    try {
      if(enabled && !projectId && account?.role!=="admin") throw new Error("Select one of your analyses to view its usage. Global analytics are administrator-only.");
      const response = await getCostMetrics(projectId);
      if (version !== requestVersion.current) return;
      setMetrics(response);
      setSelectedRunId((current) =>
        response.runs.some((run) => run.id === current)
          ? current
          : (response.runs[0]?.id ?? null),
      );
    } catch (loadError) {
      if (version === requestVersion.current) setError(errorMessage(loadError));
    } finally {
      if (version === requestVersion.current) setIsLoading(false);
    }
  }, [projectId,enabled,account]);

  useEffect(() => {
    const invalidateRequests = () => {
      requestVersion.current++;
    };
    const timer = window.setTimeout(() => {
      setProjectId(getActiveProjectId());
      setScopeReady(true);
    }, 0);
    const unsubscribe = subscribeToActiveProject((next) => {
      invalidateRequests();
      setProjectId(next);
      setMetrics(null);
      setSelectedRunId(null);
    });
    return () => {
      window.clearTimeout(timer);
      unsubscribe();
      invalidateRequests();
    };
  }, []);
  useEffect(() => {
    if (!scopeReady) return;
    const timer = window.setTimeout(() => {
      void loadMetrics();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadMetrics, scopeReady]);

  const selectedRun = useMemo(
    () =>
      metrics?.runs.find((run) => run.id === selectedRunId) ??
      metrics?.runs[0] ??
      null,
    [metrics, selectedRunId],
  );

  const averages = useMemo(
    () => ({
      retrieval: metrics?.analytics?.latencies?.retrieval?.mean_ms ?? null,
      llm: metrics?.analytics?.latencies?.gemini_inference?.mean_ms ?? null,
    }),
    [metrics],
  );

  return (
    <main className="page-container engineering-view">
      <div className="mx-auto max-w-7xl space-y-8">
        <PageHeading
          eyebrow="Engineering / Read-only"
          title="LLM Observability"
          icon="chart"
          description="Trace generation cost, latency and evidence usage."
          action={
            <button
              className="button-secondary"
              onClick={() => void loadMetrics()}
              disabled={isLoading}
            >
              <Icon name="refresh" size={15} />
              {isLoading ? "Refreshing..." : "Refresh telemetry"}
            </button>
          }
        />
        <div className="engineering-meta flex flex-wrap gap-3 justify-between items-center">
          <p className="muted text-sm">
            {projectId
              ? `Active project ${shortId(projectId)}`
              : "All projects"}{" "}
            / Stored observations only
          </p>
          {isLoading ? (
            <span role="status" className="muted text-sm">
              Loading observations...
            </span>
          ) : error ? (
            <span className="muted text-sm">Refresh incomplete</span>
          ) : (
            <CoverageBadge run={metrics?.runs[0] ?? null} />
          )}
        </div>
        <details className="notice text-sm observations-note">
          <summary>About these observations</summary>
          <p>
            Totals and latency samples reflect the entire API scope, independently of recent-history pagination. Inference excludes deterministic responses and historical unknown invocation counts. Actual billed cost is unavailable. Refreshing does not trigger inference.
          </p>
        </details>
        {error ? <ErrorBanner message={error} onRetry={loadMetrics} /> : null}

        {isLoading && !metrics ? (
          <DashboardSkeleton />
        ) : metrics ? (
          <>
            {error && (
              <p className="notice">
                Showing previously loaded observations. They may be out of date.
              </p>
            )}
            <SummaryCards metrics={metrics} averages={averages} />
            <OperationCoverage metrics={metrics} />
            <div className="engineering-grid">
              <UsagePanel metrics={metrics} averages={averages} />
              <RunInspection run={selectedRun} />
            </div>
            <RunHistory
              runs={metrics.runs}
              selectedRunId={selectedRun?.id ?? null}
              onSelect={setSelectedRunId}
            />
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
      label: "Application operations",
      value: formatInteger(metrics.totals.total_operations ?? metrics.totals.event_count),
      note: `${metrics.totals.model_invocations ?? 0} reported model invocations / ${metrics.runs.length} recent runs`,
    },
    {
      label: "Reported token subtotal",
      value: formatInteger(metrics.totals.total_tokens),
      note: `${formatInteger(metrics.totals.input_tokens)} in · ${formatInteger(metrics.totals.output_tokens)} out`,
    },
    {
      label: metrics.totals.cost_status === "partial" ? "Partial inference estimate" : "Inference estimate",
      value: formatCost(metrics.totals.estimated_cost_usd ?? metrics.totals.priced_subtotal_usd ?? null),
      note:
        metrics.totals.cost_status === "partial" ? "Partial subtotal / incomplete pricing" : metrics.totals.estimated_cost_usd === null
          ? "Estimate unavailable / inspect coverage"
          : "Paid-tier equivalent / not actual billing",
    },
    {
      label: "Mean Gemini inference latency",
      value:
        averages.llm === null ? "Unavailable" : formatDuration(averages.llm),
      note: `${metrics.analytics?.latencies?.gemini_inference?.samples ?? 0} invocation samples / ${formatDuration(averages.retrieval)} retrieval · ${formatDuration(averages.llm)} LLM`,
    },
  ];

  return (
    <section className="engineering-stats" aria-label="LLM operations summary">
      {cards.map((card, index) => (
        <article key={card.label} className="engineering-stat">
          <span className="stat-icon">
            <Icon
              name={["tokens", "chart", "cost", "clock"][index]}
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

function UsagePanel({
  metrics,
  averages,
}: {
  metrics: CostMetricsResponse;
  averages: { retrieval: number | null; llm: number | null };
}) {
  const totalTokens = metrics.totals.input_tokens != null && metrics.totals.output_tokens != null ? metrics.totals.input_tokens + metrics.totals.output_tokens : 0;
  const inputShare = totalTokens > 0 ? (metrics.totals.input_tokens ?? 0) / totalTokens : null;
  const outputShare = totalTokens > 0 ? (metrics.totals.output_tokens ?? 0) / totalTokens : null;

  return (
    <section className="usage-panel rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
            Usage signals
          </p>
          <h2 className="mt-2 text-xl font-semibold">Reported token mix and separate timing populations</h2>
        </div>
        <p className="text-xs text-slate-500">
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
            share={null}
          />
          <SignalBar
            label="Average LLM generation"
            value={formatDuration(averages.llm)}
            share={null}
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
    <div className="mb-5 last:mb-0" data-signal={label}>
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-mono text-xs text-slate-500">{value}</span>
      </div>
      {share !== null && <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-teal-500"
          style={{ width: `${bounded * 100}%` }}
        />
      </div>}
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
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
        History
      </p>
      <h2 className="mt-2 text-xl font-semibold">Recent intelligence operations</h2>
      <div className="mt-5 max-h-[760px] space-y-3 overflow-y-auto pr-1">
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
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">
                    {run.operation_type?.replaceAll("_", " ") ?? friendlyPrompt(run.prompt_name)}
                  </p>
                  <p className="mt-1 truncate text-xs text-slate-500">
                    {run.llm_model}
                  </p>
                </div>
                <RunState run={run} />
              </div>
              <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-600">
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
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
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
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="mb-4 space-y-2 text-sm">
        <p>{run.operation_type?.replaceAll("_", " ") ?? "Legacy operation / classification unavailable"}</p>
        <p>{run.provider_invocation_count == null ? "Historical invocation count unknown" : `${run.provider_invocation_count} ${run.execution_mode === "runtime" ? "actual provider invocations" : "recorded invocation markers"}`} / {run.execution_mode ?? "legacy mode unknown"}</p>
        <p>End-to-end: {formatDuration(run.end_to_end_latency_ms ?? null)} / context: {formatDuration(run.context_latency_ms ?? null)}</p>
        {run.cost_events?.map((event,index) => <div className="rounded-lg border p-3" key={index}>
          <strong>Inference estimate: {event.estimate_details?.status ?? "legacy estimate / identity unverified"}</strong>
          <p>{formatCost(event.estimated_cost_usd)} / {event.estimate_details?.service_tier ?? "tier unknown"} / {event.estimate_details?.policy_version ?? "historical policy unknown"}</p>
          {Object.entries(event.estimate_details?.components ?? {}).map(([name,value]) => <p key={name}>{name.replaceAll("_", " ")}: {formatCost(value)}</p>)}
          <p>{event.estimate_details?.reason ?? "Historical estimate retained without recalculation."}</p>
        </div>)}
        <details><summary>Usage categories and estimate provenance</summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({usage: run.telemetry?.usage ?? null, estimates: run.cost_events ?? []}, null, 2)}</pre>
        </details>
      </div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
            Inspection
          </p>
          <h2 className="mt-2 text-xl font-semibold">Run telemetry</h2>
        </div>
        <span className="font-mono text-[14px] text-slate-500">
          {shortId(run.id)}
        </span>
      </div>

      <div className="telemetry-grid mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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

      <details className="technical-details">
        <summary>Retrieval balance & reliability signals</summary>
        <div className="run-reliability grid gap-6">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
              Retrieval balance
            </h3>
            <div className="mt-3 space-y-2">
              {sourceEntries.map(([source, count]) => (
                <div
                  key={source}
                  className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm"
                >
                  <span>{friendlyLabel(source)}</span>
                  <span className="font-mono text-xs text-slate-500">
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
            <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
              Reliability signals
            </h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <SignalPill
                label="LangSmith trace"
                value={Boolean(run.langsmith_trace_id)}
              />
              <SignalPill label="Extraction cache hit" value={run.cache_hit} />
              <SignalPill label="Extraction cache miss" value={run.cache_miss} />
              <SignalPill
                label="Embedding reused"
                value={run.embedding_reused}
              />
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
      </details>
      <details className="technical-details">
        <summary>Provider & trace identifiers</summary>
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
      </details>
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
          : "min-w-0 rounded-2xl border border-slate-200 bg-slate-50 p-4"
      }
    >
      <p className="text-[14px] font-semibold uppercase tracking-[0.12em] text-slate-500">
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
    <div className="signal-pill flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs">
      <span className="text-slate-600">{label}</span>
      <span
        className={`font-semibold ${
          state === "unknown"
            ? "text-slate-500"
            : positive
              ? "text-emerald-600"
              : "text-amber-600"
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
          ? "bg-emerald-100 text-emerald-800"
          : "bg-amber-100 text-amber-800"
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
          ? "bg-emerald-100 text-emerald-700"
          : "bg-amber-100 text-amber-700"
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
      className="flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 sm:flex-row sm:items-center sm:justify-between"
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

function EmptyState({
  text,
  compact = false,
}: {
  text: string;
  compact?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border border-dashed border-slate-300 text-center text-sm text-slate-500 ${
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
            className="h-32 animate-pulse rounded-2xl bg-slate-200"
          />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-3xl bg-slate-200" />
    </div>
  );
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
    minimumFractionDigits: parsed > 0 && parsed < 0.01 ? 8 : 2,
    maximumFractionDigits: 10,
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

function formatInteger(value: number | null): string {
  if (value === null) return "Unavailable";
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


function OperationCoverage({metrics}: {metrics: CostMetricsResponse}) {
  const totals = metrics.totals;
  return <section className="rounded-2xl border border-slate-200 bg-white p-5 text-sm space-y-3">
    <h2 className="font-semibold">Pricing coverage and timing populations</h2>
    <p>{totals.priced_inference_events ?? 0} of {totals.inference_events ?? 0} inference events with stored estimates; {totals.unpriced_inference_events ?? 0} unpriced. Status: {totals.cost_status ?? "legacy unknown"}.</p>
    <p>{totals.deterministic_operations ?? 0} deterministic operations / {totals.legacy_invocation_unknown ?? 0} historical operations with unknown invocation counts. Token totals are sums of reported categories; inspect each operation for usage completeness.</p>
    <p>{totals.legacy_estimate_events ?? 0} historical estimates lack verified pricing provenance. Verified policy coverage: {totals.verified_pricing_coverage == null ? "Not measured" : `${Math.round(totals.verified_pricing_coverage * 100)}%`}.</p>
    <p>Estimated paid-tier equivalent only. Actual billed cost unavailable. Missing prices, partial usage and unresolved tiers remain unknown.</p>
    <div className="grid gap-3 sm:grid-cols-2">{Object.entries(metrics.analytics?.latencies ?? {}).map(([name,value]) => <div key={name} className="rounded-lg border p-3">
      <strong>{name.replaceAll("_", " ")}</strong><p>{value.samples} samples / mean {formatDuration(value.mean_ms)} / p50 {formatDuration(value.p50_ms)} / p95 {formatDuration(value.p95_ms)}</p>
    </div>)}</div>
    <details><summary>Operation mix and daily reported activity</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({operations:metrics.analytics?.operations,daily:metrics.analytics?.daily},null,2)}</pre></details>
    <p className="text-slate-600">{metrics.analytics?.latency_policy}</p>
  </section>;
}
