"use client";
import { useEffect, useState, useRef } from "react";
import { decisionCopy,comparisonValue,objectiveNames,outcomeLabel } from "@/lib/intelligence-copy";
import { ResultBanner } from "./ResultBanner";
import { Icon } from "./ui";
import { getCreatorInsightSummary } from "@/lib/api";
import { getComparisonObjective, setComparisonObjective } from "@/lib/app-session";
import type { ComparisonObjective, CreatorInsightSummaryResponse } from "@/types/project";

export const OBJECTIVES = [["balanced", "Balanced"], ["reach", "Reach"], ["engagement", "Engagement"], ["creative_quality", "Creative Quality"]] as const;
export function GoalComparisonPanel({ summary, onChange, onCreativeReview, creativeBusy=false }: { summary: CreatorInsightSummaryResponse; onChange?: (value: CreatorInsightSummaryResponse) => void; onCreativeReview?:()=>void; creativeBusy?:boolean }) {
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
  const copy=decision?decisionCopy(decision):null;
  return <section className="ui-panel comparison-decision" aria-label="Canonical comparison" aria-busy={busy}>
    <div className="decision-heading"><div><p className="eyebrow">Creator intelligence</p><h2><Icon name="compare" size={22}/> Performance snapshot</h2></div>
      <label className="objective-picker">Comparison objective <select disabled={busy||!onChange} value={decision?.selected_objective??"balanced"} onChange={e=>setComparisonObjective(summary.project_id,e.target.value as ComparisonObjective)}>{OBJECTIVES.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
    </div>
    {busy&&<p role="status" className="muted text-sm mt-3">Updating your comparison...</p>}
    {error&&<p role="alert" className="mt-3 text-rose-800">{error}</p>}
    {decision&&copy?<>
      <ResultBanner title={copy.title} description={copy.description} winner={Boolean(decision.winner_slot)} detail={<><span className="signal-label">{copy.objective}</span><strong>{decision.eligibility.status==="eligible"?"Assessed":"Review needed"}</strong></>}/>
      <dl className="objective-values">{(["content_1","content_2"] as const).map(slot=><div key={slot}><dt>{slot==="content_1"?"Content 1":"Content 2"}</dt><dd>{comparisonValue(decision.raw_objective_values[slot],decision.objective_units)}</dd></div>)}</dl>
      {decision.outcome==="insufficient_evidence"&&["balanced","creative_quality"].includes(decision.selected_objective)&&<div className="creative-next-step"><span className="signal-icon"><Icon name="bulb" size={22}/></span><div><strong>Bring the creative story into focus</strong><p>Review both openings, audience value and calls to action. Uses your AI allowance and may incur provider costs.</p></div>{onCreativeReview?<button className="button-primary" type="button" disabled={creativeBusy} onClick={onCreativeReview}>{creativeBusy?"Queuing review...":"Run creative review"}</button>:<a className="button-secondary" href="/analyze#insights">Open creative review</a>}</div>}
      <details className="detail-disclosure mt-4"><summary>Evidence, comparison method and limitations</summary>
        <p className="mt-3 text-sm muted">{decision.explanation}</p>
        {decision.missing_evidence.length>0&&<p className="mt-3 text-sm muted">Required evidence: {decision.missing_evidence.join("; ")}</p>}
        <div className="mt-3 grid gap-3 sm:grid-cols-2">{Object.entries(decision.dimension_leaders).map(([key,value])=><article key={key} className="rounded-md border border-slate-200 p-3"><h3 className="font-semibold">{objectiveNames[key]??key.replaceAll("_"," ")}</h3><p>{outcomeLabel(value.outcome)}</p><p className="text-sm muted">{value.explanation}</p></article>)}</div>
        <p className="mt-3 text-xs break-words">Decision policy: {decision.decision_policy_version} / Metric policy: {decision.metric_policy_version} / Creative policy: {decision.creative_policy_version??"Awaiting review"}</p>
        <p className="mt-3 text-sm muted">{decision.limitations.join(" ")}</p>
      </details>
    </>:<p className="mt-3 muted">Your comparison will appear when its evidence is available.</p>}
  </section>;
}
