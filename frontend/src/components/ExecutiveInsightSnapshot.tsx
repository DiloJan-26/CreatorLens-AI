import type { CreatorInsightSummaryResponse } from "@/types/project";
import { Icon } from "./ui";
import { ResultBanner } from "./ResultBanner";
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
  const performance = c.confirmed_metric_winner;
  const slot = performance?.match(/^content\s+([12])\b/i)?.[1];
  const title = slot
    ? `Content ${slot} leads on confirmed public metrics.`
    : performance && /tie/i.test(performance)
      ? "The confirmed public metrics support a tie."
      : "Available evidence limits the performance comparison.";
  return (
    <section className="insight-conclusion">
      <ResultBanner
        title={title}
        winner={Boolean(slot)}
        description="Based on extracted public metrics. Creative causation is not established."
        detail={
          <>
            <span className="signal-label">Assessment</span>
            <strong>Rule-based</strong>
            <span className="muted">Deterministic signals</span>
          </>
        }
      />
      <details className="verdict-rationale">
        <summary>What the evidence supports</summary>
        <p>{c.main_reason || "Available evidence limits this comparison."}</p>
        <dl className="verdict-grid mt-5">
          {[
            ["Public metrics", c.confirmed_metric_winner],
            ["Hook assessment", c.hook_winner],
            ["Creative structure", c.creative_structure_winner],
            ["Creator efficiency", c.creator_efficiency_winner],
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
      </details>
    </section>
  );
}

export function ComparisonHighlights({
  summary,
}: {
  summary: CreatorInsightSummaryResponse | null;
}) {
  if (!summary) return null;
  const c = summary.comparison;
  return (
    <section
      className="comparison-highlights"
      aria-labelledby="key-insights-title"
    >
      <h2 id="key-insights-title">Key insights</h2>
      <div className="highlight-grid">
        {[
          {
            icon: "trend",
            title: "Public performance",
            value: c.confirmed_metric_winner || "Unavailable",
            note: "Confirmed public metrics; platforms may differ.",
          },
          {
            icon: "target",
            title: "Opening hook",
            value: c.hook_winner || "Unavailable",
            note: "Deterministic hook assessment, not measured retention.",
          },
          {
            icon: "bulb",
            title: "Opportunity",
            value:
              c.top_recommendations[0] ||
              "More evidence is needed before recommending changes.",
            note: "A creative hypothesis to test.",
          },
        ].map((item) => (
          <article key={item.title} className="highlight-card">
            <span className={`highlight-icon ${item.icon}`}>
              <Icon name={item.icon} size={23} />
            </span>
            <div>
              <h3>{item.title}</h3>
              <p>{item.value}</p>
              <span className="muted">{item.note}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
