"use client";
import {useEffect,useState} from "react";
import {getCreatorInsightSummary} from "@/lib/api";
import {setComparisonObjective} from "@/lib/app-session";
import {comparisonValue,outcomeLabel} from "@/lib/intelligence-copy";
import type {CreatorInsightSummaryResponse} from "@/types/project";
import {Icon} from "./ui";
import {ResultBanner} from "./ResultBanner";
const OPTIONS=[["reach","Reach","trend"],["engagement","Like rate","target"],["creative_quality","Opening & messaging","bulb"]] as const;
export function GoalComparisonPanel({summary,onChange,objective="reach"}:{summary:CreatorInsightSummaryResponse;onChange?:(value:CreatorInsightSummaryResponse)=>void;onCreativeReview?:()=>void;creativeBusy?:boolean;objective?:"reach"|"engagement"|"creative_quality"}){
 const [selected,setSelected]=useState(objective),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
 useEffect(()=>{if(!onChange)return;let active=true;const timer=setTimeout(()=>{setComparisonObjective(summary.project_id,selected);
 if(summary.goal_comparison?.selected_objective!==selected){setBusy(true);getCreatorInsightSummary(summary.project_id,selected).then(value=>{if(active){onChange(value);setError(null);}}).catch(()=>{if(active)setError("Comparison unavailable. Try again.");}).finally(()=>{if(active)setBusy(false);});}else setBusy(false);
 },0);return()=>{active=false;clearTimeout(timer);};},[summary.project_id,summary.goal_comparison?.selected_objective,selected,onChange]);
 const observed=summary.intelligence;
 if(observed){
 const key=selected==="reach"?"reach":selected==="engagement"?"like_rate":null;
 const current=key?observed.decisions[key]:null;
 const leader=current?.winner_slot;
 return <section className="ui-panel outcome-panel" aria-label="Canonical comparison" aria-busy={busy}>
 <div className="objective-tabs" role="group" aria-label="Comparison objective">{OPTIONS.map(([id,label,icon])=><button type="button" key={id} aria-pressed={selected===id} disabled={busy} onClick={()=>setSelected(id)}><Icon name={icon} size={17}/>{label}</button>)}</div>
 <ResultBanner title={!current?"Explore opening & messaging":leader?`Content ${leader.slice(-1)} leads ${selected==="reach"?"reach":"like rate"}`:current.outcome==="tie"?"Within the comparison threshold":"Available evidence"} winner={Boolean(leader)} description={current?.explanation??"Inspect each video's wording and supported experiments in Insights."}/>
 {current&&<div className="outcome-values">{(["content_1","content_2"] as const).map((slot,index)=><div key={slot}><span>Content {index+1}</span><strong>{comparisonValue(current.values[slot],current.units)}</strong></div>)}</div>}
 <p className="muted text-sm mt-3">{current?.status==="insufficient_evidence"?current.missing_inputs.join(" "):selected==="reach"?"Observed lifetime views; publishing periods may differ.":selected==="engagement"?"Likes per recorded view; comments are assessed independently.":"Textual patterns describe structure, without a creativity score."}</p>
 {error&&<p role="alert">{error}</p>}</section>;
 }
 const current=summary.goal_comparison,decision=current?.selected_objective===selected?current:current?.objective_decisions?.[selected];
 const values=decision&&("raw_objective_values" in decision?decision.raw_objective_values:decision.values);
 const units=selected==="reach"?"views":selected==="engagement"?"percent":"points_out_of_10";
 const ready=decision?.outcome==="content_1"||decision?.outcome==="content_2";
 return <section className="ui-panel outcome-panel" aria-label="Canonical comparison" aria-busy={busy} data-objective={selected}>
 <div className="objective-tabs" role="group" aria-label="Comparison objective">{OPTIONS.map(([id,label,icon])=><button type="button" key={id} aria-pressed={selected===id} disabled={busy} onClick={()=>setSelected(id)}><Icon name={icon} size={17}/>{label}</button>)}</div>
 <ResultBanner title={decision?outcomeLabel(decision.outcome):"Comparison unavailable"} winner={ready} description={selected==="reach"?"Based on confirmed public views.":selected==="engagement"?"Based on comparable public interaction rates.":"Based on validated caption evidence."} detail={<><span className="signal-label">Assessment</span><strong>{OPTIONS.find(([id])=>id===selected)?.[1]}</strong><span className="muted">{ready?"Evidence supported":"Evidence limited"}</span></>}/>
 <div className="outcome-values">{(["content_1","content_2"] as const).map((slot,index)=><div key={slot}><span>Content {index+1}</span><strong>{comparisonValue(values?.[slot],units)}</strong></div>)}</div>
 <p className="muted text-sm mt-3">{decision?.outcome==="incomparable"?"These sources are not directly comparable.":decision?.outcome==="tie"?"The difference is within the comparison threshold.":!ready?selected==="reach"?"Views are unavailable for one or both videos.":selected==="engagement"?"Complete interaction counts and 1,000+ views per video required.":"Creative review needed. Open Insights to review both videos.":selected==="reach"?"Confirmed lifetime views.":selected==="engagement"?"Observed interaction rate.":"Caption-based creative assessment."}</p>
 {error&&<p role="alert" className="mt-3 text-sm text-rose-800">{error}</p>}</section>;
}
