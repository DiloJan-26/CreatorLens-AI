"use client";
import { useEffect, useRef, useState } from "react";
import { getDemoCapabilities, getSemanticAnalysis, requestSemanticAnalysis } from "@/lib/api";
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
    getDemoCapabilities().then(v => { if (!controller.signal.aborted) setAllowed(v.provider_calls_enabled); }).catch(() => {});
    getSemanticAnalysis(projectId, slot, controller.signal).then(setAnalysis).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Semantic status unavailable."); });
    return () => controller.abort();
  }, [projectId, slot]);
  useEffect(() => {
    if (analysis?.status !== "pending") return;
    if (polls.current >= 60) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      polls.current++;
      try {
        const value = await getSemanticAnalysis(projectId, slot, controller.signal);
        if (controller.signal.aborted) return;
        setAnalysis(value);
        if (value.status === "ready") readyCallback.current();
        if (value.status === "pending" && polls.current >= 60) setError("Polling paused after 60 checks. Refresh status to continue; no new inference is started.");
      } catch { if (!controller.signal.aborted) setError("Status polling paused. Refresh to retry the read-only check."); }
    }, 2000);
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
    try { setAnalysis(await requestSemanticAnalysis(projectId, slot, analysis?.status === "failed")); }
    catch (e) { setError(e instanceof Error ? e.message : "Semantic request failed."); }
    finally { submitting.current = false; setBusy(false); }
  }
  const state = analysis?.status === "unavailable" && !analysis.snapshot_id ? "Not analyzed / no compatible snapshot" : analysis?.status ?? "Loading";
  return <section className="ui-panel p-4" aria-label={`${slot} semantic analysis`}>
    <h3 className="font-semibold">{slot === "content_1" ? "Content 1" : "Content 2"} / Semantic creative analysis</h3>
    <p className="mt-2" role="status">{state}</p>
    <p className="mt-2 text-sm muted">{analysis?.model_id ? `Model: ${analysis.model_id} / ` : ""}{analysis?.cache_hit ? "Cached validated snapshot." : analysis?.reason ?? "Only compatible evidence can support creative scoring."}</p>
    {analysis?.error_code && <p className="mt-2 text-amber-900">{analysis.error_code === "STALE_INPUT" ? "Evidence changed; the old job cannot supply current features." : analysis.error_code}</p>}
    {error && <p role="alert" className="mt-2 text-rose-800">{error}</p>}
    <p className="mt-3 text-sm muted">Provider: Gemini Developer API. Generation may incur provider charges. Page loads and status checks never generate features.</p>
    {!allowed && <p className="mt-2 text-sm">Provider generation is disabled in this restricted demo. Use the labeled offline fixtures to demonstrate semantic analysis.</p>}
    <div className="mt-3 flex flex-wrap gap-3"><button className="button-secondary" disabled={busy} onClick={() => void refresh()}>Refresh status</button><button className="button-primary" disabled={!allowed || busy || analysis?.status === "pending" || analysis?.status === "ready"} onClick={() => void generate()}>{analysis?.status === "failed" ? "Retry semantic analysis" : "Generate semantic features"}</button></div>
    {analysis?.assessments?.length ? <details className="detail-disclosure mt-3"><summary>Validated model-derived features</summary><dl className="mt-3 grid gap-2">{analysis.assessments.map(feature => <div key={feature.feature}><dt className="font-medium capitalize">{feature.feature.replaceAll("_", " ")}</dt><dd>{feature.value} / {feature.status}</dd></div>)}</dl></details> : null}
    {analysis?.limitations?.length ? <p className="mt-3 text-sm muted">{analysis.limitations.join(" ")}</p> : null}
  </section>;
}
