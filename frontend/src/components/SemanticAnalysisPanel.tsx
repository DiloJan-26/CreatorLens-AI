"use client";
import { uiConfig } from "@/lib/ui-config";
import { useEffect, useRef, useState } from "react";
import { getProviderStatus, getSemanticAnalysis, requestSemanticAnalysis } from "@/lib/api";
import type { ContentSlot, SemanticAnalysis } from "@/types/project";

export function SemanticAnalysisPanel({ projectId, slot, onReady }: { projectId: string; slot: ContentSlot; onReady: () => void }) {
  const [analysis, setAnalysis] = useState<SemanticAnalysis | null>(null);
  const [allowed, setAllowed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitting = useRef(false);
  const polls = useRef(0);
  const readyCallback = useRef(onReady);
  useEffect(() => { readyCallback.current = onReady; }, [onReady]);
  useEffect(() => {
    const controller = new AbortController();
    getProviderStatus().then(v => { if (!controller.signal.aborted) setAllowed(v.provider_calls_enabled); }).catch(() => {});
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
  async function generate() {
    if (!allowed || submitting.current || analysis?.status === "pending" || analysis?.status === "ready") return;
    submitting.current = true; setBusy(true); setError(null); polls.current = 0;
    try { const value=await requestSemanticAnalysis(projectId, slot, analysis?.status === "failed"); setAnalysis(value); if(value.status==="ready")readyCallback.current(); }
    catch (e) { setError(e instanceof Error ? e.message : "Semantic request failed."); }
    finally { submitting.current = false; setBusy(false); }
  }
  const state = analysis?.error_code === "EVIDENCE_UNAVAILABLE" ? "More caption evidence needed"
    : analysis?.error_code === "STALE_INPUT" ? "Evidence changed"
    : analysis?.status === "unavailable" && !analysis.snapshot_id ? "Ready for creative review"
    : analysis ? {pending:"Review in progress",ready:"Creative review ready",failed:"Review needs attention",unavailable:"Review unavailable"}[analysis.status] : "Loading review status";
  return <section className="ui-panel p-4" aria-label={`${slot} semantic analysis`}>
    <h3 className="font-semibold">{slot === "content_1" ? "Content 1" : "Content 2"} / Creative review</h3>
    <p className="mt-2 font-medium" role="status">{state}</p>
    {error && <p role="alert" className="mt-2 text-rose-800">{error}</p>}
    <p className="mt-3 text-sm muted">Uses your AI analysis allowance. Existing results are reused when the evidence is unchanged.</p>
    {!allowed && <p className="mt-2 text-sm">Creative review is not available right now. Your existing results remain accessible.</p>}
    <div className="mt-3 flex flex-wrap gap-3"><button className="button-secondary" disabled={busy} onClick={() => void refresh()}>Refresh status</button><button className="button-primary" disabled={!allowed || busy || analysis?.status === "pending" || analysis?.status === "ready"} onClick={() => void generate()}>{analysis?.status === "failed" ? "Retry creative review" : "Review this video"}</button></div>
    {analysis?.assessments?.length ? <details className="detail-disclosure mt-3"><summary>Validated model-derived features</summary><dl className="mt-3 grid gap-2">{analysis.assessments.map(feature => <div key={feature.feature}><dt className="font-medium capitalize">{feature.feature.replaceAll("_", " ")}</dt><dd>{feature.value} / {feature.status}</dd></div>)}</dl></details> : null}
    {analysis && <details className="detail-disclosure mt-3"><summary>Source quality and review details</summary><p className="mt-3 text-sm muted">Model: {analysis.model_id ?? "Not recorded"}. {analysis.cache_hit ? "Reused validated assessment." : ""}</p><p className="mt-2 text-sm muted">{analysis.reason}</p>{analysis.error_code && <p className="mt-2 text-sm muted">Review status: {analysis.error_code}</p>}<p className="mt-2 text-sm muted">{analysis.limitations?.join(" ")}</p></details>}
  </section>;
}
