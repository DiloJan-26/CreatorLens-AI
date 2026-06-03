export type ProgressStatus = "pending" | "running" | "complete" | "failed";

export type AnalysisProgressStep = {
  id: string;
  label: string;
  status: ProgressStatus;
};

type AnalysisProgressProps = {
  steps: AnalysisProgressStep[];
  isVisible: boolean;
};

export function AnalysisProgress({ steps, isVisible }: AnalysisProgressProps) {
  if (!isVisible) {
    return null;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Analysis progress
          </p>
          <h2 className="mt-2 text-base font-semibold text-slate-950">
            Building your creator intelligence workspace
          </h2>
        </div>
        <StatusChip status={overallStatus(steps)} />
      </div>

      <ol className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {steps.map((step) => (
          <li
            key={step.id}
            className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3"
          >
            <span
              className={`h-2.5 w-2.5 rounded-full ${statusDotClass(step.status)}`}
            />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-950">
                {step.label}
              </p>
              <p className="mt-0.5 text-xs capitalize text-slate-500">
                {step.status}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function StatusChip({ status }: { status: ProgressStatus }) {
  return (
    <span
      className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold capitalize ${statusChipClass(status)}`}
    >
      {status}
    </span>
  );
}

function overallStatus(steps: AnalysisProgressStep[]): ProgressStatus {
  if (steps.some((step) => step.status === "failed")) {
    return "failed";
  }

  if (steps.every((step) => step.status === "complete")) {
    return "complete";
  }

  if (steps.some((step) => step.status === "running")) {
    return "running";
  }

  return "pending";
}

function statusDotClass(status: ProgressStatus): string {
  if (status === "complete") {
    return "bg-emerald-500";
  }

  if (status === "running") {
    return "bg-sky-500";
  }

  if (status === "failed") {
    return "bg-rose-500";
  }

  return "bg-slate-300";
}

function statusChipClass(status: ProgressStatus): string {
  if (status === "complete") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }

  if (status === "running") {
    return "border-sky-200 bg-sky-50 text-sky-800";
  }

  if (status === "failed") {
    return "border-rose-200 bg-rose-50 text-rose-800";
  }

  return "border-slate-200 bg-slate-50 text-slate-600";
}
