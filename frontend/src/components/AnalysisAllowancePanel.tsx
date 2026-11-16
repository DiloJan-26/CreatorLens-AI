"use client";
import { useEffect,useState } from "react";
import { useAccount } from "./AccountProvider";
import { getProjectUsage,completeAnalysis } from "@/lib/api";
export function AnalysisAllowancePanel({projectId}:{projectId:string}){
  const {refresh}=useAccount();
  const [usage,setUsage]=useState<Awaited<ReturnType<typeof getProjectUsage>>|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  useEffect(()=>{void getProjectUsage(projectId).then(setUsage).catch(()=>setError("Usage status unavailable."));},[projectId]);
  async function complete(metricsOnly:boolean){setBusy(true);setError(null);try{await completeAnalysis(projectId,metricsOnly);setUsage(await getProjectUsage(projectId));await refresh();}catch(e){setError(e instanceof Error?e.message:"Completion unavailable.");}finally{setBusy(false);}}
  return <details className="analysis-allowance ui-panel p-4 my-4"><summary><strong>Analysis status</strong><span className="muted ml-3">{usage?.analysis_state==="completed"?"Saved":usage?"Review in progress":"Loading"}</span></summary>
    <div aria-label="Analysis allowance" className="mt-3"><p>{usage?.analysis_state==="completed"?"Your analysis is saved in your workspace.":"Save after creative review, or save a metrics summary. Saving metrics only closes creative review for this analysis."}</p>
    <p className="muted mt-2">{usage?.assistant_remaining??"Unavailable"} AI responses available after completion. Metric questions do not use this allowance.</p>
    {usage&&["reserved","processing"].includes(usage.analysis_state)&&<div className="flex flex-wrap gap-3 mt-3"><button className="button-primary" disabled={busy} onClick={()=>void complete(false)}>Save full analysis</button><button className="button-secondary" disabled={busy} onClick={()=>void complete(true)}>Save metrics summary</button></div>}
    <button className="button-quiet mt-3" onClick={()=>void getProjectUsage(projectId).then(setUsage).catch(()=>setError("Usage status unavailable."))}>Refresh usage</button>{error&&<p role="alert" className="mt-3">{error}</p>}</div></details>;
}
