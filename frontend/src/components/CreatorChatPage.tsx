"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {PlatformIcon} from "./PlatformIcon";
import {PageHeading,Notice} from "./ui";
import {CreatorChatPanel} from "./CreatorChatPanel";
import {AnalysisAllowancePanel} from "./AnalysisAllowancePanel";
import {getProject,getProjectIngestionStatus} from "@/lib/api";
import {getActiveProjectId,subscribeToActiveProject} from "@/lib/app-session";
import {uiConfig} from "@/lib/ui-config";
import type {ProjectDetailResponse} from "@/types/project";
export function CreatorChatPage(){
 const [projectId,setProjectId]=useState<string|null>(null),[detail,setDetail]=useState<ProjectDetailResponse|null>(null),[status,setStatus]=useState<string|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[retry,setRetry]=useState(0);
 useEffect(()=>{const timer=setTimeout(()=>{setProjectId(getActiveProjectId());setLoading(false);},0);const off=subscribeToActiveProject(setProjectId);return()=>{clearTimeout(timer);off();};},[]);
 useEffect(()=>{if(!projectId)return;let active=true;const timer=setTimeout(()=>{setLoading(true);setError(null);setDetail(null);setStatus(null);Promise.all([getProject(projectId),getProjectIngestionStatus(projectId).catch(()=>null)]).then(([next,job])=>{if(active){setDetail(next);setStatus(job?.status??null);}}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Conversation unavailable.");}).finally(()=>{if(active)setLoading(false);});},0);return()=>{active=false;clearTimeout(timer);};},[projectId,retry]);
 useEffect(()=>{if(!projectId||!status||["READY","PARTIAL_READY","FAILED"].includes(status))return;let active=true,count=0;let timer:ReturnType<typeof setTimeout>;
 const poll=async()=>{try{const job=await getProjectIngestionStatus(projectId);if(!active)return;setStatus(job.status);if(["READY","PARTIAL_READY","FAILED"].includes(job.status))return;}catch{}if(active&&++count<uiConfig.semanticPollLimit)timer=setTimeout(poll,uiConfig.pollIntervalMs);};timer=setTimeout(poll,uiConfig.pollIntervalMs);return()=>{active=false;clearTimeout(timer);};},[projectId,status]);
 return <main className="page-container assistant-page"><PageHeading eyebrow="Creator workspace" title="AI Assistant" icon="chat" action={<Link className="button-secondary" href="/analyze">View comparison</Link>}/>
 {loading?<Notice>Loading conversation...</Notice>:!projectId?<section className="ui-panel"><h2>Choose a comparison</h2><Link className="button-primary mt-4" href="/workspace">Your analyses</Link></section>:error?<Notice tone="error">{error}<button className="button-secondary" onClick={()=>setRetry(n=>n+1)}>Retry</button></Notice>:detail&&<><AnalysisAllowancePanel key={projectId} projectId={projectId}/><div className="chat-layout"><aside className="chat-context"><h2 className="text-base font-semibold">Active comparison</h2><div className="grid gap-3 mt-4">{detail.content_items.map(item=><article key={item.slot} className="chat-context-card"><p className="platform-label"><PlatformIcon platform={item.platform}/>{item.slot==="content_1"?"Content 1":"Content 2"}</p><h3 className="font-semibold mt-3">{item.title??"Untitled video"}</h3><p className="muted text-sm mt-2">{item.creator??"Creator unavailable"}</p></article>)}</div><Link href="/analyze#evidence" className="button-quiet mt-4">View evidence</Link></aside><CreatorChatPanel key={projectId} projectId={projectId} indexReady={status===null||status==="READY"||status==="PARTIAL_READY"}/></div>{status&&!["READY","PARTIAL_READY"].includes(status)&&<p className="notice mt-3">{status==="FAILED"?"Evidence processing failed.":"Preparing your evidence..."}<Link href="/analyze"> View analysis</Link></p>}</>}
 </main>;
}
