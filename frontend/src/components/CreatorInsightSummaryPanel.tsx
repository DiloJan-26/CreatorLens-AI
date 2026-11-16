"use client";
import {useEffect,useState} from "react";
import {Icon} from "./ui";
import {getCreatorInsightSummary} from "@/lib/api";
import type {CreatorInsightSummaryResponse} from "@/types/project";
import {CreatorRecommendationList} from "./CreatorRecommendationList";
export function CreatorInsightSummaryPanel({projectId,initialSummary,onSummaryLoaded}:{projectId:string|null;indexReady?:boolean;initialSummary?:CreatorInsightSummaryResponse|null;onSummaryLoaded?:(summary:CreatorInsightSummaryResponse)=>void}){
 const [summary,setSummary]=useState<CreatorInsightSummaryResponse|null>(null);
 const [error,setError]=useState<string|null>(null);
 useEffect(()=>{if(!projectId||initialSummary?.project_id===projectId)return;let active=true;getCreatorInsightSummary(projectId,"creative_quality").then(value=>{if(active){setSummary(value);onSummaryLoaded?.(value);}}).catch(()=>{if(active)setError("Insights unavailable.");});return()=>{active=false;};},[projectId,initialSummary?.project_id,onSummaryLoaded]);
 const value=initialSummary?.project_id===projectId?initialSummary:summary?.project_id===projectId?summary:null;
 if(error)return <p role="alert">{error}</p>;
 return value?<section className="ui-panel"><div className="insights-heading"><div><p className="eyebrow">Creator intelligence</p><h2 className="text-xl font-semibold mt-2">Creator Insight Summary</h2></div><Icon name="chart" size={24}/></div><div className="grid gap-4 md:grid-cols-2 my-5">{[value.content_1,value.content_2].map(content=>content&&<article key={content.slot} className="creator-score-card"><p className="eyebrow">{content.label}</p><h3 className="text-lg font-semibold mt-2">Creator insight <span className="score-number">{content.semantic_scoring?.overall.score==null?"Unavailable":`${content.semantic_scoring.overall.score.toFixed(1)} / 10`}</span></h3><dl className="metric-grid mt-4">{[["Reach",content.scoring?.reach.score],["Engagement",content.scoring?.engagement.score],["Public performance",content.scoring?.public_performance.score],["Audience efficiency",content.scoring?.creator_efficiency.score],["Creative quality",content.semantic_scoring?.creative_structure.score]].map(([label,score])=><div key={String(label)}><dt className="muted text-xs">{label}</dt><dd className="font-semibold mt-1">{typeof score==="number"?`${score.toFixed(1)} / 10`:"Unavailable"}</dd></div>)}</dl></article>)}</div>{value.creator_recommendations?<CreatorRecommendationList bundle={value.creator_recommendations} contents={[value.content_1,value.content_2]}/>:<p className="notice">No supported recommendations yet.</p>}</section>:null;
}
