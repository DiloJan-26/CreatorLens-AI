"use client";
import { useEffect,useState } from "react";
import { useAccount } from "./AccountProvider";
import { getProjectUsage,completeAnalysis } from "@/lib/api";
export function AnalysisAllowancePanel({projectId,showResponseCount=true}:{projectId:string;showResponseCount?:boolean}){
  const {refresh}=useAccount();
  const [usage,setUsage]=useState<Awaited<ReturnType<typeof getProjectUsage>>|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  useEffect(()=>{void getProjectUsage(projectId).then(setUsage).catch(()=>setError("Usage status unavailable."));},[projectId]);
  async function complete(metricsOnly:boolean){setBusy(true);setError(null);try{await completeAnalysis(projectId,metricsOnly);setUsage(await getProjectUsage(projectId));await refresh();}catch(e){setError(e instanceof Error?e.message:"Completion unavailable.");}finally{setBusy(false);}}
  if(usage?.analysis_state==="completed"&&!showResponseCount&&!error)return null;
  return <section className="analysis-save-row" aria-label="Analysis allowance">{(usage?.analysis_state!=="completed"||showResponseCount)&&<span>{usage?.analysis_state==="completed"?`${usage.assistant_remaining} AI responses available`:usage?"Unlock AI explanations":"Loading status..."}</span>}{usage&&["reserved","processing"].includes(usage.analysis_state)&&<div className="flex flex-wrap gap-2"><button className="button-primary" disabled={busy} onClick={()=>void complete(false)}>Save analysis</button></div>}{error&&<p role="alert">{error}</p>}</section>;
}
