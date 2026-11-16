"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {useAccount} from "./AccountProvider";
import {PageHeading,Icon,EmptyState} from "./ui";
import {PlatformIcon} from "./PlatformIcon";
import {getAccountUsage,listOwnedProjects} from "@/lib/api";
import {setActiveProjectId} from "@/lib/app-session";
import type {ProjectRecord} from "@/types/project";
export function AccountWorkspace(){
 const {account,refresh}=useAccount();
 const [revision,setRevision]=useState(0),[data,setData]=useState<{owner:string;projects:ProjectRecord[];usage:Awaited<ReturnType<typeof getAccountUsage>>}|null>(null),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(true);
 useEffect(()=>{if(!account?.id)return;let active=true;const owner=account.id;const timer=setTimeout(()=>{setLoading(true);setError(null);Promise.all([listOwnedProjects(),getAccountUsage()]).then(([projects,usage])=>{if(active)setData({owner,projects:projects.projects,usage});}).catch(()=>{if(active)setError("Could not load your analyses. Please refresh.");}).finally(()=>{if(active)setLoading(false);});},0);return()=>{active=false;clearTimeout(timer);};},[account?.id,revision]);
 const current=data?.owner===account?.id?data:null, balance=current?.usage.balance??account?.usage;
 const projects=current?.projects??[];
 const exhausted=Boolean(balance&&balance.available===0&&balance.reserved===0);
 const action=exhausted?<button className="button-secondary" onClick={()=>window.dispatchEvent(new Event("creatorlens_quota_exhausted"))}>Free analysis limit reached</button>:balance&&balance.reserved===0?<Link className="button-primary" href="/analyze?new=1"><Icon name="compare" size={17}/>Compare two videos</Link>:undefined;
 return <main className="page-container project-workspace"><PageHeading eyebrow="Your workspace" title={`Welcome${account?.display_name?`, ${account.display_name}`:""}`} description="Your comparisons, insights and next creative ideas." icon="home" action={action}/>
 <div className="workspace-usage-grid">{[["Available",balance?.available,"compare"],["In progress",balance?.reserved,"clock"],["Completed",balance?.completed,"check"]].map(([label,count,icon])=><article className="ui-panel usage-tile" key={String(label)}><span className="signal-icon"><Icon name={String(icon)}/></span><div><p className="muted text-sm">{label}</p><strong>{count??"Unavailable"}</strong></div></article>)}</div>
 <div className="workspace-plan-line"><span>{balance?`${balance.available} of ${balance.granted} analyses available`:"Loading balance..."}</span><span>Free plan | Subscription plans coming soon.</span></div>
 {balance?.reserved?<p className="notice mb-5" role="status">An analysis is in progress. Open it below to continue.</p>:null}
 {error&&<p className="notice notice-error mb-4" role="alert">{error}</p>}
 <div className="project-section-heading"><h2>Your analyses <span className="muted text-sm">{current?projects.length:""}</span></h2><button className="button-quiet" disabled={loading} onClick={()=>void refresh().then(()=>setRevision(n=>n+1))}><Icon name="refresh" size={15}/>Refresh account balance</button></div>
 {loading&&!current?<p role="status" className="notice">Loading your analyses...</p>:projects.length?<div className="owned-project-grid">{projects.map(project=><article className="ui-panel owned-project-card" key={project.project_id}><div className="project-card-top"><span className="platform-label"><PlatformIcon platform={project.content_1_platform}/><PlatformIcon platform={project.content_2_platform}/></span><span className="extraction-state">{statusLabel(project.status)}</span></div><h3>Video comparison</h3><p className="muted text-xs">{new Date(project.created_at).toLocaleDateString(undefined,{month:"short",day:"numeric",year:"numeric"})}</p><ol className="project-video-list">{[project.content_1_url,project.content_2_url].map((url,index)=><li key={index}><span>{index+1}</span><p title={url}>{url.replace(/^https?:\/\/(www\.)?/,"")}</p></li>)}</ol><Link href="/analyze" className="button-secondary" onClick={()=>setActiveProjectId(project.project_id)}>Open comparison <Icon name="arrow" size={16}/></Link></article>)}</div>:!error?<EmptyState title="Your next insight starts here">Compare two videos to build your private analysis library.</EmptyState>:null}
 </main>;
}
function statusLabel(status:string){return ({created:"New",ready:"Ready",indexed:"Ready",partial_ready:"Evidence ready",failed:"Needs attention",processing:"In progress"} as Record<string,string>)[status.toLowerCase()]??status.replaceAll("_"," ");}
