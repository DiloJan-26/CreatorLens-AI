"use client";
import { Icon } from "./ui";
import { uiConfig } from "@/lib/ui-config";
import { useEffect, useRef, useState } from "react";
import { getSemanticAnalysis } from "@/lib/api";
import type { ContentSlot, SemanticAnalysis } from "@/types/project";

export function SemanticAnalysisPanel({ projectId, slot, onReady, onStatusChange, compact=false }: { projectId: string; slot: ContentSlot; onReady: () => void; onStatusChange?: (slot:ContentSlot,value:SemanticAnalysis)=>void; compact?:boolean }) {
  const [analysis, setAnalysis] = useState<SemanticAnalysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const statusCallback=useRef(onStatusChange);
  useEffect(()=>{statusCallback.current=onStatusChange;},[onStatusChange]);
  useEffect(()=>{if(analysis)statusCallback.current?.(slot,analysis);},[analysis,slot]);
  const submitting = useRef(false);
  const polls = useRef(0);
  const readyCallback = useRef(onReady);
  useEffect(() => { readyCallback.current = onReady; }, [onReady]);
  useEffect(() => {
    const controller = new AbortController();
    getSemanticAnalysis(projectId, slot, controller.signal).then(value => { if (!controller.signal.aborted) setAnalysis(value); }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Semantic status unavailable."); });
    return () => controller.abort();
  }, [projectId, slot]);
  useEffect(()=>{
    const controller=new AbortController();
    const queued=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail.projectId!==projectId||detail.slot!==slot)return;
      polls.current=0;getSemanticAnalysis(projectId,slot,controller.signal).then(value=>{if(!controller.signal.aborted){setAnalysis(value);if(value.status==="ready")readyCallback.current();}}).catch(()=>{if(!controller.signal.aborted)setError("Could not refresh creative review status.");});};
    window.addEventListener("creatorlens_semantic_queued",queued);
    return ()=>{controller.abort();window.removeEventListener("creatorlens_semantic_queued",queued);};
  },[projectId,slot]);
  useEffect(() => {
    if (analysis?.status !== "pending") return;
    if (polls.current >= uiConfig.semanticPollLimit) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      polls.current++;
      try {
        const value = await getSemanticAnalysis(projectId, slot, controller.signal);
        if (controller.signal.aborted) return;
        setAnalysis(value);
        if (value.status === "ready") readyCallback.current();
        if (value.status === "pending" && polls.current >= uiConfig.semanticPollLimit) setError(`Polling paused after ${uiConfig.semanticPollLimit} checks. Refresh status to continue; no new inference is started.`);
      } catch { if (!controller.signal.aborted) setError("Status polling paused. Refresh to retry the read-only check."); }
    }, uiConfig.pollIntervalMs);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [analysis, projectId, slot]);
  async function refresh() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError(null); polls.current = 0;
    try { const value = await getSemanticAnalysis(projectId, slot); setAnalysis(value); if (value.status === "ready") readyCallback.current(); } catch { setError("Could not refresh semantic status."); }
    finally { submitting.current = false; setBusy(false); }
  }
  const state = analysis?.error_code === "EVIDENCE_UNAVAILABLE" ? "More caption evidence needed"
    : analysis?.error_code === "STALE_INPUT" ? "Evidence changed"
    : analysis?.status === "unavailable" && !analysis.snapshot_id ? "Ready for creative review"
    : analysis ? {pending:"Review in progress",ready:"Creative review ready",failed:"Review needs attention",unavailable:"Review unavailable"}[analysis.status] : "Loading review status";
  if(compact)return <article className="review-slot" aria-label={`${slot} semantic analysis`}><span className={`review-dot review-${analysis?.status??"loading"}`}/><div><strong>{slot==="content_1"?"Content 1":"Content 2"}</strong><p role="status">{state}</p>{error&&<p role="alert" className="review-error">{error}</p>}</div><button type="button" className="icon-button" disabled={busy} onClick={()=>void refresh()} aria-label={`Refresh ${slot==="content_1"?"Content 1":"Content 2"} review`}><Icon name="refresh" size={16}/></button></article>;
  return <section className="ui-panel p-4" aria-label={`${slot} semantic analysis`}>
    <h3 className="font-semibold">{slot === "content_1" ? "Content 1" : "Content 2"} / Creative review</h3>
    <p className="mt-2 font-medium" role="status">{state}</p>
    {error && <p role="alert" className="mt-2 text-rose-800">{error}</p>}
    <button type="button" className="button-quiet mt-3" disabled={busy} onClick={()=>void refresh()}>Refresh</button>
    {analysis?.assessments?.length ? <dl className="creative-feature-list mt-3">{analysis.assessments.filter(feature=>feature.status==="assessed").map(feature=><div key={feature.feature}><dt>{feature.feature.replaceAll("_"," ")}</dt><dd>{feature.value==="absent"?"Not present":feature.value==="partial"?"Developing":feature.value==="clear"?"Clear":feature.value}</dd></div>)}</dl>:null}
  </section>;
}
