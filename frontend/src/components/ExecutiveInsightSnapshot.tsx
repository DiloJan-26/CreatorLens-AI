import type { CreatorInsightSummaryResponse } from "@/types/project";
import { ResultBanner } from "./ResultBanner";

export function ExecutiveInsightSnapshot({ summary, isLoading = false }: { summary: CreatorInsightSummaryResponse | null; isLoading?: boolean }) {
  if (!summary) return <div className="notice">{isLoading ? "Preparing supported insights..." : "Comparison evidence is not available yet."}</div>;
  const decision = summary.goal_comparison;
  if (!decision) return <div className="notice">Canonical V2 comparison is unavailable. Legacy winners are not substituted.</div>;
  return <section className="insight-conclusion"><ResultBanner title={decision.winner_slot ? `${decision.winner_slot === "content_1" ? "Content 1" : "Content 2"} leads under ${decision.selected_objective.replaceAll("_", " ")}.` : `${decision.selected_objective.replaceAll("_", " ")}: ${decision.outcome.replaceAll("_", " ")}`} winner={Boolean(decision.winner_slot)} description={decision.explanation} detail={<><span className="signal-label">Assessment</span><strong>{decision.eligibility.status.replaceAll("_", " ")}</strong><span className="muted">Canonical decision</span></>} /></section>;
}
export function ComparisonHighlights({ summary }: { summary: CreatorInsightSummaryResponse | null }) {
  const decision = summary?.goal_comparison;
  if (!decision) return null;
  return <section className="comparison-highlights" aria-label="Independent comparison signals"><h2>Independent signals</h2><div className="highlight-grid">{Object.entries(decision.dimension_leaders).slice(0, 3).map(([name, value]) => <article className="highlight-card" key={name}><div><h3 className="capitalize">{name.replaceAll("_", " ")}</h3><p>{value.outcome.replaceAll("_", " ")}</p><span className="muted">{value.explanation}</span></div></article>)}</div></section>;
}
