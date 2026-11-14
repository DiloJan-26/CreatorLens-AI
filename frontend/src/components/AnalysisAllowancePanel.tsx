"use client";
import { useEffect,useState } from "react";
import { useAccount } from "./AccountProvider";
import { getProjectUsage,completeAnalysis } from "@/lib/api";
export function AnalysisAllowancePanel({projectId}:{projectId:string}){
  const {enabled,refresh}=useAccount();
  const [usage,setUsage]=useState<Awaited<ReturnType<typeof getProjectUsage>>|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  useEffect(()=>{if(enabled)void getProjectUsage(projectId).then(setUsage).catch(()=>setError("Usage status unavailable."));},[enabled,projectId]);
  if(!enabled)return null;
  async function complete(metricsOnly:boolean){setBusy(true);setError(null);try{await completeAnalysis(projectId,metricsOnly);setUsage(await getProjectUsage(projectId));await refresh();}catch(e){setError(e instanceof Error?e.message:"Completion unavailable.");}finally{setBusy(false);}}
  return <section className="ui-panel p-4 my-4" aria-label="Analysis allowance"><p>Analysis: {usage?.analysis_state.replaceAll("_"," ")??"Loading"}{usage?.completion_mode?` / ${usage.completion_mode.replaceAll("_"," ")}`:""}</p><p className="muted mt-2">Assistant: {usage?.assistant_remaining??"Unavailable"} admitted Gemini attempts remaining. Deterministic questions do not use this allowance.</p>{usage&&["reserved","processing"].includes(usage.analysis_state)&&<><p className="muted mt-3">Completion consumes one reserved comparison credit. Metrics-only completion requires sufficient confirmed metrics for both videos.</p><div className="flex flex-wrap gap-3 mt-3"><button className="button-secondary" disabled={busy} onClick={()=>void complete(false)}>Complete validated analysis</button><button className="button-secondary" disabled={busy} onClick={()=>void complete(true)}>Complete as metrics-only</button></div></>}<button className="button-secondary mt-3" onClick={()=>void getProjectUsage(projectId).then(setUsage).catch(()=>setError("Usage status unavailable."))}>Refresh usage</button>{error&&<p role="alert" className="mt-3">{error}</p>}</section>;
}
