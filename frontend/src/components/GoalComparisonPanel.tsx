"use client";
import {useEffect,useState} from "react";
import {getCreatorInsightSummary} from "@/lib/api";
import {setComparisonObjective} from "@/lib/app-session";
import {comparisonValue,outcomeLabel} from "@/lib/intelligence-copy";
import type {CreatorInsightSummaryResponse} from "@/types/project";
import {Icon} from "./ui";
const OPTIONS=[["reach","Reach","trend"],["engagement","Engagement","target"],["creative_quality","Creative quality","bulb"]] as const;
export function GoalComparisonPanel({summary,onChange,objective="reach"}:{summary:CreatorInsightSummaryResponse;onChange?:(value:CreatorInsightSummaryResponse)=>void;onCreativeReview?:()=>void;creativeBusy?:boolean;objective?:"reach"|"engagement"|"creative_quality"}){
 const [selected,setSelected]=useState(objective),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
 useEffect(()=>{if(!onChange)return;let active=true;const timer=setTimeout(()=>{setComparisonObjective(summary.project_id,selected);
 if(summary.goal_comparison?.selected_objective!==selected){setBusy(true);getCreatorInsightSummary(summary.project_id,selected).then(value=>{if(active){onChange(value);setError(null);}}).catch(()=>{if(active)setError("Comparison unavailable. Try again.");}).finally(()=>{if(active)setBusy(false);});}else setBusy(false);
 },0);return()=>{active=false;clearTimeout(timer);};},[summary.project_id,summary.goal_comparison?.selected_objective,selected,onChange]);
 const current=summary.goal_comparison,decision=current?.selected_objective===selected?current:current?.objective_decisions?.[selected];
 const values=decision&&("raw_objective_values" in decision?decision.raw_objective_values:decision.values);
 const units=selected==="reach"?"views":selected==="engagement"?"percent":"points_out_of_10";
 const ready=decision?.outcome==="content_1"||decision?.outcome==="content_2";
 return <section className="ui-panel outcome-panel" aria-label="Canonical comparison" aria-busy={busy} data-objective={selected}>
 <div className="objective-tabs" role="group" aria-label="Comparison objective">{OPTIONS.map(([id,label,icon])=><button type="button" key={id} aria-pressed={selected===id} disabled={busy} onClick={()=>setSelected(id)}><Icon name={icon} size={17}/>{label}</button>)}</div>
 <div className="outcome-header"><span className="signal-icon"><Icon name={ready?"trophy":selected==="reach"?"trend":"evidence"} size={23}/></span><div><p className="eyebrow">{OPTIONS.find(([id])=>id===selected)?.[1]}</p><h2>{decision?outcomeLabel(decision.outcome):"Comparison unavailable"}</h2></div></div>
 <div className="outcome-values">{(["content_1","content_2"] as const).map((slot,index)=><div key={slot}><span>Content {index+1}</span><strong>{comparisonValue(values?.[slot],units)}</strong></div>)}</div>
 <p className="muted text-sm mt-3">{decision?.outcome==="incomparable"?"These sources are not directly comparable.":decision?.outcome==="tie"?"The difference is within the comparison threshold.":!ready?selected==="reach"?"Views are unavailable for one or both videos.":selected==="engagement"?"Complete interaction counts and 1,000+ views per video required.":"Creative review needed. Open Insights to review both videos.":selected==="reach"?"Confirmed lifetime views.":selected==="engagement"?"Observed interaction rate.":"Caption-based creative assessment."}</p>
 {error&&<p role="alert" className="mt-3 text-sm text-rose-800">{error}</p>}</section>;
}
