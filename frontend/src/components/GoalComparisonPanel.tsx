"use client";
import { useEffect, useState, useRef } from "react";
import { getCreatorInsightSummary } from "@/lib/api";
import { getComparisonObjective, setComparisonObjective } from "@/lib/app-session";
import type { ComparisonObjective, CreatorInsightSummaryResponse } from "@/types/project";

export const OBJECTIVES = [["balanced", "Balanced"], ["reach", "Reach"], ["engagement", "Engagement"], ["creative_quality", "Creative Quality"]] as const;
export function GoalComparisonPanel({ summary, onChange }: { summary: CreatorInsightSummaryResponse; onChange?: (value: CreatorInsightSummaryResponse) => void }) {
  const decision = summary.goal_comparison;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  useEffect(() => {
    let active = true;
    async function sync() {
      const id = ++requestId.current;
      setBusy(true); setError(null);
      try {
        const next = await getCreatorInsightSummary(summary.project_id, getComparisonObjective(summary.project_id));
        if (active && id === requestId.current) onChange?.(next);
      } catch { if (active && id === requestId.current) setError("Could not load this objective. The previous assessment remains visible."); }
      finally { if (active && id === requestId.current) setBusy(false); }
    }
    function changed(event: Event) {
      if ((event as CustomEvent).detail.projectId === summary.project_id) void sync();
    }
    window.addEventListener("creatorlens_objective_changed", changed);
    return () => { active = false; window.removeEventListener("creatorlens_objective_changed", changed); };
  }, [summary.project_id, onChange]);
  return <section className="ui-panel p-5 my-5" aria-label="Canonical comparison" aria-busy={busy}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xl font-semibold">Goal-aware comparison</h2>
      <label className="text-sm font-medium">Comparison objective <select className="rounded-md border border-slate-300 p-2 ml-2 max-w-full" disabled={busy || !onChange} value={decision?.selected_objective ?? "balanced"} onChange={e => setComparisonObjective(summary.project_id, e.target.value as ComparisonObjective)}>{OBJECTIVES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
    </div>
    {busy && <p role="status" className="mt-3 muted">Loading objective-specific evidence...</p>}
    {error && <p role="alert" className="mt-3 text-rose-800">{error}</p>}
    {decision ? <>
      <p className="mt-4 font-semibold text-lg">{decision.outcome.replaceAll("_", " ")}{decision.winner_slot ? " leads under this objective" : ""}</p>
      <p className="mt-2 leading-7">{decision.explanation}</p>
      <dl className="mt-4 grid gap-4 sm:grid-cols-2">{(["content_1", "content_2"] as const).map(slot => <div key={slot}><dt>{slot === "content_1" ? "Content 1" : "Content 2"}</dt><dd className="text-xl font-semibold">{decision.raw_objective_values[slot] == null ? "Unavailable" : decision.raw_objective_values[slot].toLocaleString()} <span className="text-sm font-normal">{decision.objective_units}</span></dd></div>)}</dl>
      {decision.missing_evidence.length > 0 && <p className="mt-4 text-amber-900">Missing evidence: {decision.missing_evidence.join("; ")}</p>}
      <details className="detail-disclosure mt-4"><summary>Independent dimension leaders and policy</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">{Object.entries(decision.dimension_leaders).map(([key, value]) => <article key={key} className="rounded-md border border-slate-200 p-3"><h3 className="capitalize font-semibold">{key.replaceAll("_", " ")}</h3><p>{value.outcome.replaceAll("_", " ")}</p><p className="text-sm muted">{value.explanation}</p><p className="text-sm muted">{value.limitations.join(" ")}</p></article>)}</div>
        <p className="mt-3 text-sm break-words">Decision: {decision.decision_policy_version} / Metrics: {decision.metric_policy_version} / Creative: {decision.creative_policy_version ?? "Not assessable"}</p>
      </details>
      <p className="mt-4 text-sm muted">{decision.limitations.join(" ")}</p>
    </> : <p className="mt-3">Canonical V2 decision unavailable. Legacy results are not substituted.</p>}
  </section>;
}
