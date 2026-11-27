"use client";
import { useEffect, useState } from "react";
import { useAccount } from "./AccountProvider";
import { getProjectUsage, completeAnalysis } from "@/lib/api";

export function AnalysisAllowancePanel({projectId,ready=false,showResponseCount=true}:{projectId:string;ready?:boolean;showResponseCount?:boolean}){
  const {refresh}=useAccount();
  const [usage,setUsage]=useState<Awaited<ReturnType<typeof getProjectUsage>>|null>(null);
  const [error,setError]=useState<string|null>(null);
  useEffect(()=>{
    let active=true;
    async function load(){
      try{
        let value=await getProjectUsage(projectId);
        if(!active)return;
        // Compatibility for already indexed analyses from before automatic settlement.
        // This POST validates readiness on the server and never invokes a model.
        if(ready && ["reserved","processing"].includes(value.analysis_state)){
          await completeAnalysis(projectId,false);
          value=await getProjectUsage(projectId);
        }
        if(!active)return;
        setUsage(value);setError(null);
        if(ready && value.analysis_state==="completed")await refresh();
      }catch(e){if(active)setError(e instanceof Error?e.message:"Analysis status unavailable.");}
    }
    void load();
    return()=>{active=false;};
  },[projectId,ready,refresh]);
  if(error)return <p role="alert" className="notice">{error}</p>;
  if(!showResponseCount || usage?.analysis_state!=="completed")return null;
  return <section className="analysis-save-row" aria-label="Assistant allowance"><span>{usage.assistant_remaining} AI responses available</span></section>;
}
