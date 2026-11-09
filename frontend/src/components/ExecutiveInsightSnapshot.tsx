import type { CreatorInsightSummaryResponse } from "@/types/project";
export function ExecutiveInsightSnapshot({
  summary,
  isLoading = false,
}: {
  summary: CreatorInsightSummaryResponse | null;
  isLoading?: boolean;
}) {
  if (!summary)
    return (
      <div className="notice">
        {isLoading
          ? "Preparing insights from available evidence..."
          : "Insights are not available for this comparison yet. Review the extracted content below."}
      </div>
    );
  const c = summary.comparison;
  return (
    <section className="insight-conclusion">
      <p className="eyebrow">What the evidence supports</p>
      <h2 className="text-xl">
        {c.main_reason || "Available evidence limits this comparison."}
      </h2>
      <dl className="verdict-grid mt-5">
        {[
          ["Public metrics", c.confirmed_metric_winner],
          ["Hook assessment", c.hook_winner],
          ["Heuristic insight score", c.overall_insight_winner],
        ].map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs muted">{label}</dt>
            <dd className="font-semibold mt-1">{value || "Unavailable"}</dd>
          </div>
        ))}
      </dl>
      {c.top_recommendations[0] && (
        <p className="mt-5 text-sm">
          <strong>Try next: </strong>
          {c.top_recommendations[0]}
        </p>
      )}
      <p className="muted text-xs mt-4">
        {c.confidence_note ||
          "Cross-platform metrics are not directly equivalent."}
      </p>
    </section>
  );
}
