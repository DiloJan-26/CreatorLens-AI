import type { CreatorInsightSummaryResponse } from "@/types/project";

type ExecutiveInsightSnapshotProps = {
  summary: CreatorInsightSummaryResponse | null;
  isLoading?: boolean;
};

export function ExecutiveInsightSnapshot({
  summary,
  isLoading = false,
}: ExecutiveInsightSnapshotProps) {
  const recommendation = summary?.comparison.top_recommendations[0];

  return (
    <section className="rounded-lg border border-teal-200 bg-white p-5 shadow-md shadow-teal-900/5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Executive Insight Snapshot
          </p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">
            What matters most from this comparison
          </h2>
        </div>
        <span className="w-fit rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-800">
          Cited creator insights
        </span>
      </div>

      {isLoading && !summary ? (
        <p className="mt-5 rounded-md border border-sky-200 bg-sky-50 px-3 py-3 text-sm text-sky-800">
          Generating creator insights from confirmed public evidence...
        </p>
      ) : null}

      {!isLoading && !summary ? (
        <p className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-6 text-slate-600">
          Run an analysis to see the metric winner, hook winner, top
          recommendation, and confidence note.
        </p>
      ) : null}

      {summary ? (
        <>
          <p className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm leading-6 text-slate-700">
            {summary.comparison.main_reason ||
              "Comparison limited by unavailable public metrics."}
          </p>

          <dl className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <SnapshotMetric
              label="Confirmed metric winner"
              value={summary.comparison.confirmed_metric_winner}
            />
            <SnapshotMetric
              label="Hook winner"
              value={summary.comparison.hook_winner}
            />
          <SnapshotMetric
              label="Creator Insight Score winner"
              value={summary.comparison.overall_insight_winner}
            />
            <SnapshotMetric
              label="Top improvement opportunity"
              value={recommendation}
            />
          </dl>

          <p className="mt-5 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm leading-6 text-amber-900">
            <span className="font-semibold">Metadata Confidence: </span>
            {summary.comparison.confidence_note ||
              "Comparison limited by unavailable public metrics."}
          </p>
        </>
      ) : null}
    </section>
  );
}

function SnapshotMetric({
  label,
  value,
}: {
  label: string;
  value?: string | null;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-3">
      <dt className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </dt>
      <dd className="mt-2 break-words text-sm font-semibold text-slate-950">
        {value || "Unavailable"}
      </dd>
    </div>
  );
}
