"use client";
import Link from "next/link";
import {useEffect,useState} from "react";
import {Icon} from "./ui";
import {getCreatorInsightSummary} from "@/lib/api";
import type {CreatorInsightSummaryResponse} from "@/types/project";

export function CreatorInsightSummaryPanel({projectId,initialSummary,onSummaryLoaded}:{projectId:string|null;indexReady?:boolean;initialSummary?:CreatorInsightSummaryResponse|null;onSummaryLoaded?:(summary:CreatorInsightSummaryResponse)=>void}){
 const [loaded,setLoaded]=useState<CreatorInsightSummaryResponse|null>(null);
 const [error,setError]=useState<string|null>(null);
 useEffect(()=>{if(!projectId||initialSummary?.project_id===projectId)return;let active=true;
 getCreatorInsightSummary(projectId,"reach").then(value=>{if(active){setLoaded(value);onSummaryLoaded?.(value);setError(null);}}).catch(()=>{if(active)setError("Could not load insights. Try again.");});return()=>{active=false;};},[projectId,initialSummary?.project_id,onSummaryLoaded]);
 const summary=initialSummary?.project_id===projectId?initialSummary:loaded?.project_id===projectId?loaded:null;
 const data=summary?.intelligence;
 if(error)return <p role="alert" className="notice notice-error">{error}</p>;
 if(!data)return <section className="ui-panel insight-empty"><Icon name="chart" size={24}/><h2>Your creator insights</h2><p>{summary?"Refresh this analysis to load the current evidence policy.":"Preparing your findings..."}</p></section>;
 const metrics=[["views","Views"],["like_rate","Like rate"],["comment_rate","Comment rate"],["audience_efficiency","Views / subscriber"]];
 const visible=metrics.filter(([key])=>data.contents.some(c=>c.values[key]!=null));
 return <div className="insights-workbench">
 <section className="ui-panel"><div className="insight-section-heading"><span className="highlight-icon trend"><Icon name="chart" size={24}/></span><div><h2>Your performance signals</h2><p>Observed results, with each signal assessed independently.</p></div></div>
 <div className="insight-table-wrap"><table className="insight-assessment-table"><thead><tr><th scope="col">Signal</th>{data.contents.map(c=><th scope="col" key={c.content_id}><span>Content {c.slot.slice(-1)}</span><small>{c.title}</small></th>)}</tr></thead><tbody>{visible.map(([key,label])=><tr key={key}><th scope="row">{label}</th>{data.contents.map(c=><td key={c.content_id}><strong>{c.values[key]==null?"\u2014":key==="views"?c.values[key]!.toLocaleString():`${c.values[key]!.toFixed(key==="audience_efficiency"?2:3)}${key.endsWith("rate")?"%":"\u00d7"}`}</strong></td>)}</tr>)}</tbody></table></div>
 {!visible.length&&<p>Public metrics were not returned. Available text observations appear below.</p>}
 <div className="comparison-highlights"><div className="highlight-grid">{Object.values(data.decisions).filter(d=>d.status==="eligible"||d.status==="descriptive").map(d=><article className="highlight-card" key={d.dimension}><Icon name={d.dimension==="reach"?"trend":"target"} size={20}/><div><h3>{d.dimension.replaceAll("_"," ")}</h3><p>{d.outcome==="tie"?"Within the comparison threshold":d.winner_slot?`Content ${d.winner_slot.slice(-1)} leads`:"Descriptive comparison"}</p></div></article>)}</div></div>
 <p className="insight-footnote">Lifetime counts reflect different audiences and publishing periods. Likes and comments do not establish audience sentiment.</p></section>
 <section><div className="insight-section-heading"><Icon name="bulb" size={23}/><div><h2>Opening &amp; messaging structure</h2><p>Patterns found in the available wording.</p></div></div><div className="video-insight-grid">{data.contents.map(c=><article className="ui-panel video-insight-card" key={c.content_id}><p className="eyebrow">Content {c.slot.slice(-1)}</p><h3>{c.title}</h3>{c.observations.length?<ul className="video-findings">{c.observations.map((o,index)=>{const ref=c.evidence.find(e=>o.evidence_ids.includes(e.evidence_id));return <li key={o.id}><p><Icon name={o.matched?"check":"evidence"} size={15}/> {o.observation}</p>{ref&&c.observations.findIndex(other=>other.evidence_ids.includes(ref.evidence_id))===index&&<blockquote className="muted text-sm">&ldquo;{ref.text}&rdquo;{ref.start_time!=null&&ref.end_time!=null&&<span> ({ref.start_time.toFixed(1)}&ndash;{ref.end_time.toFixed(1)}s)</span>}</blockquote>}</li>;})}</ul>:<p>{c.limitations[0]??"The available text does not support these checks."}</p>}</article>)}</div></section>
 <section className="ui-panel"><div className="insight-section-heading"><Icon name="bulb" size={24}/><div><h2>What to try next</h2><p>Small experiments grounded in each video.</p></div></div>{data.recommendations.length?<div className="video-findings">{data.recommendations.map(r=><article className="video-insight-card" key={r.id}><p className="eyebrow">Content {r.target_slot.slice(-1)} &middot; {r.priority.label} priority</p><h3>{r.title}</h3><p>{r.observation}</p><p><strong>Experiment: </strong>{r.experiment}</p><p className="muted text-sm">{r.limitation}</p></article>)}</div>:<p>No specific wording change is supported. Use the observations to decide what is worth testing.</p>}</section>
 <div className="insight-assistant-link"><span><Icon name="chat" size={20}/> Discuss your findings and explore alternative wording.</span><Link href="/chat" className="button-primary">Ask the Assistant <Icon name="arrow" size={16}/></Link></div>
 </div>;
}
