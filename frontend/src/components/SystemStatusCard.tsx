type SystemStatusCardProps = {
  statusText: string;
  isChecking: boolean;
  onCheck: () => void;
};

export function SystemStatusCard({
  statusText,
  isChecking,
  onCheck,
}: SystemStatusCardProps) {
  const isOk = statusText.toLowerCase().startsWith("ok");

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            System
          </p>
          <p
            className={`mt-2 text-sm ${
              isOk ? "text-emerald-700" : "text-slate-600"
            }`}
          >
            System status: {statusText}
          </p>
        </div>
        <button
          type="button"
          onClick={onCheck}
          disabled={isChecking}
          className="inline-flex h-11 items-center justify-center rounded-md bg-slate-950 px-5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isChecking ? "Checking..." : "Check System"}
        </button>
      </div>
    </section>
  );
}
