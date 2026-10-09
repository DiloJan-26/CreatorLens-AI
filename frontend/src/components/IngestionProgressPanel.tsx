import type {
  IngestionJobStatus,
  IngestionStatusResponse,
} from "@/types/project";

type IngestionProgressPanelProps = {
  status: IngestionStatusResponse | null;
  isPolling: boolean;
};

const STATUS_LABELS: Record<IngestionJobStatus, string> = {
  PENDING: "Waiting for a worker",
  EXTRACTING_METADATA: "Extracting public metadata",
  EXTRACTING_TRANSCRIPT: "Pulling transcript evidence",
  CHUNKING: "Preparing evidence chunks",
  EMBEDDING: "Creating evidence embeddings",
  INDEXING: "Indexing evidence for retrieval",
  READY: "Analysis ready",
  PARTIAL_READY: "Analysis partially ready",
  FAILED: "Analysis failed",
};

export function IngestionProgressPanel({
  status,
  isPolling,
}: IngestionProgressPanelProps) {
  if (!status) {
    return null;
  }

  const progress = Math.min(100, Math.max(0, status.progress_percent));
  const isFailed = status.status === "FAILED";
  const isPartial = status.status === "PARTIAL_READY";

  return (
    <section
      className={`rounded-lg border p-5 shadow-sm ${panelClass(status.status)}`}
      aria-live="polite"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em]">
            Background ingestion
          </p>
          <h2 className="mt-2 text-base font-semibold">
            {STATUS_LABELS[status.status]}
          </h2>
          <p className="mt-1 text-sm opacity-80">
            {isPolling ? "Checking the worker for updates..." : terminalMessage(status.status)}
          </p>
        </div>
        <span className="w-fit rounded-full border border-current/20 px-3 py-1 text-xs font-semibold">
          {progress}%
        </span>
      </div>

      <div
        className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-800"
        role="progressbar"
        aria-label="Ingestion progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${progressClass(status.status)}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-3">
        <Timestamp label="Started" value={status.started_at ?? status.created_at} />
        <Timestamp label="Last update" value={status.updated_at} />
        <Timestamp label="Completed" value={status.completed_at} />
      </dl>

      {status.retry_count > 0 ? (
        <p className="mt-3 text-xs opacity-80">
          Worker retries: {status.retry_count}
        </p>
      ) : null}

      {isFailed && status.error_message ? (
        <p className="mt-4 rounded-md border border-rose-300 bg-white/70 px-3 py-2 text-sm text-rose-900 dark:bg-slate-950/40 dark:text-rose-100">
          {status.error_message}
          {status.error_code ? ` (${status.error_code})` : ""}
        </p>
      ) : null}

      {isPartial ? (
        <p className="mt-4 rounded-md border border-amber-300 bg-white/70 px-3 py-2 text-sm text-amber-950 dark:bg-slate-950/40 dark:text-amber-100">
          Usable evidence is ready, but one or more transcript or metadata fields
          were unavailable. Missing values remain marked as unavailable.
        </p>
      ) : null}
    </section>
  );
}

function Timestamp({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt className="font-medium opacity-70">{label}</dt>
      <dd className="mt-1 font-medium">{formatLocalTime(value)}</dd>
    </div>
  );
}

function formatLocalTime(value?: string | null): string {
  if (!value) {
    return "Not yet";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function terminalMessage(status: IngestionJobStatus): string {
  if (status === "READY") {
    return "Metadata, transcripts, and the evidence index are ready.";
  }
  if (status === "PARTIAL_READY") {
    return "Available evidence is ready to use.";
  }
  if (status === "FAILED") {
    return "The worker could not complete this ingestion job.";
  }
  return "Waiting for the next worker update.";
}

function panelClass(status: IngestionJobStatus): string {
  if (status === "FAILED") {
    return "border-rose-200 bg-rose-50 text-rose-950 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-100";
  }
  if (status === "PARTIAL_READY") {
    return "border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100";
  }
  if (status === "READY") {
    return "border-emerald-200 bg-emerald-50 text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100";
  }
  return "border-sky-200 bg-sky-50 text-sky-950 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-100";
}

function progressClass(status: IngestionJobStatus): string {
  if (status === "FAILED") {
    return "bg-rose-500";
  }
  if (status === "PARTIAL_READY") {
    return "bg-amber-500";
  }
  if (status === "READY") {
    return "bg-emerald-500";
  }
  return "bg-sky-500";
}
