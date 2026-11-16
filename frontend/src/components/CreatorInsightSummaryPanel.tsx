"use client";
import {useEffect,useState} from "react";
import {getCreatorInsightSummary} from "@/lib/api";
import type {CreatorInsightSummaryResponse} from "@/types/project";
import {CreatorRecommendationList} from "./CreatorRecommendationList";
export function CreatorInsightSummaryPanel({projectId,initialSummary,onSummaryLoaded}:{projectId:string|null;indexReady?:boolean;initialSummary?:CreatorInsightSummaryResponse|null;onSummaryLoaded?:(summary:CreatorInsightSummaryResponse)=>void}){
 const [summary,setSummary]=useState<CreatorInsightSummaryResponse|null>(null);
 const [error,setError]=useState<string|null>(null);
 useEffect(()=>{if(!projectId||initialSummary?.project_id===projectId)return;let active=true;getCreatorInsightSummary(projectId,"creative_quality").then(value=>{if(active){setSummary(value);onSummaryLoaded?.(value);}}).catch(()=>{if(active)setError("Insights unavailable.");});return()=>{active=false;};},[projectId,initialSummary?.project_id,onSummaryLoaded]);
 const value=initialSummary?.project_id===projectId?initialSummary:summary?.project_id===projectId?summary:null;
 if(error)return <p role="alert">{error}</p>;
 return value?.creator_recommendations?<CreatorRecommendationList bundle={value.creator_recommendations} contents={[value.content_1,value.content_2]}/>:<p className="notice">No supported recommendations yet.</p>;
}
