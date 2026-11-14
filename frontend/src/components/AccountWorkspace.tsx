"use client";
import { useEffect,useState } from "react";
import Link from "next/link";
import { useAccount } from "./AccountProvider";
import { getAccountUsage,listOwnedProjects } from "@/lib/api";
import { setActiveProjectId } from "@/lib/app-session";
import type { ProjectRecord } from "@/types/project";
export function AccountWorkspace(){
  const {account,refresh}=useAccount();
  const [projects,setProjects]=useState<ProjectRecord[]>([]),[usage,setUsage]=useState<Awaited<ReturnType<typeof getAccountUsage>>|null>(null),[error,setError]=useState<string|null>(null);
  useEffect(()=>{
    let active=true;
    Promise.all([listOwnedProjects(),getAccountUsage()]).then(([p,u])=>{if(active){setProjects(p.projects);setUsage(u);}}).catch(()=>{if(active)setError("Could not load your analyses and usage. Please refresh.");});
    return ()=>{active=false;};
  },[]);
  const balance=usage?.balance??account?.usage;
  return <main className="page-container"><p className="eyebrow">Your workspace</p><h1 className="text-3xl font-semibold mt-3">Welcome{account?.display_name?`, ${account.display_name}`:""}</h1>
    {error&&<p role="alert" className="mt-4">{error}</p>}
    <section className="ui-panel p-5 my-6"><h2 className="text-xl font-semibold">Free plan</h2><p className="mt-3">{balance?`${balance.available} of ${balance.granted} analyses available`:"Loading balance..."}</p><p className="muted mt-2">{balance?.reserved??0} reserved / {balance?.completed??0} completed. Credits do not refresh monthly.</p>{balance?.completed===balance?.granted && balance?<button className="button-secondary mt-4" onClick={()=>window.dispatchEvent(new Event("creatorlens_quota_exhausted"))}>Free analysis limit reached</button>:balance?.reserved?<p className="mt-4" role="status">One analysis is in progress. Open it below before starting another.</p>:<Link className="button-primary mt-4" href="/analyze?new=1">Compare two videos</Link>}</section>
    <h2 className="text-xl font-semibold">Your analyses</h2><div className="grid gap-4 mt-4">{projects.map(project=><Link key={project.project_id} href="/analyze" onClick={()=>setActiveProjectId(project.project_id)} className="ui-panel p-5"><strong>{project.content_1_platform} / {project.content_2_platform}</strong><p className="muted mt-2">{project.status} / {new Date(project.created_at).toLocaleDateString()}</p><span className="text-sm">Open comparison</span></Link>)}{!projects.length&&!error&&<p>No analyses yet. Your results will appear here.</p>}</div>
    <details className="detail-disclosure mt-6"><summary>Analysis status and usage history</summary><ul className="mt-3 space-y-2">{usage?.analyses.map(value=><li key={value.id}>{value.state.replaceAll("_"," ")}{value.completion_mode?` / ${value.completion_mode.replaceAll("_"," ")}`:""}</li>)}{usage?.events.map((event,i)=><li key={event.reference_id+event.kind+i}>{event.kind.replaceAll("_"," ")} / {new Date(event.created_at).toLocaleString()}</li>)}</ul><button className="button-secondary mt-4" onClick={()=>void refresh()}>Refresh account balance</button></details>
  </main>;
}
