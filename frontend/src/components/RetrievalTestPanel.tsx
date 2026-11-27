"use client";

import { useEffect, useRef, useState } from "react";
import { retrieveProjectChunks } from "@/lib/api";
import type { ContentItem, ContentPlatform, ContentSlot, RetrievedChunk, RetrieveProjectChunksRequest, RetrieveResponse } from "@/types/project";
import { Icon, Notice } from "./ui";
import { PlatformIcon } from "./PlatformIcon";

type Source = NonNullable<RetrieveProjectChunksRequest["source_type"]>;
const sources: [Source, string][] = [["metadata", "Public metrics"], ["description", "Description"], ["hook", "Opening"], ["transcript", "Transcript passage"]];
const prompts = ["How do the videos introduce the topic?", "What public metrics are available?", "What viewer takeaway is stated?"];
export function evidenceBelongsToContent(chunk: Pick<RetrievedChunk, "slot" | "platform" | "content_id">, contents: ContentItem[]) {
  return contents.some(item => item.slot === chunk.slot && item.platform === chunk.platform &&
    (!(item.id ?? item.content_id) || !chunk.content_id || (item.id ?? item.content_id) === chunk.content_id));
}
export function evidenceTimestamp(start?: number | null, end?: number | null) {
  if (start == null || end == null || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) return null;
  const format = (n: number) => `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, "0")}`;
  return `${format(start)} - ${format(end)}`;
}

export function RetrievalTestPanel({ projectId, indexReady, contents = [] }: {
  projectId: string | null; indexReady: boolean; contents?: ContentItem[];
}) {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<ContentPlatform | "all">("all");
  const [slot, setSlot] = useState<ContentSlot | "all">("all");
  const [source, setSource] = useState<Source | "all">("all");
  const [result, setResult] = useState<RetrieveResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [visible, setVisible] = useState(6);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  function clearSearch() {
    controller.current?.abort(); controller.current = null;
    setResult(null); setError(null); setSearching(false); setVisible(6);
  }
  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId || !indexReady || !query.trim() || searching) return;
    const active = new AbortController(); controller.current?.abort(); controller.current = active;
    setSearching(true); setError(null); setResult(null); setVisible(6);
    try {
      const response = await retrieveProjectChunks(projectId, {purpose: "evidence_search", query: query.trim(), top_k: 8,
        platform: platform === "all" ? null : platform, slot: slot === "all" ? null : slot, source_type: source === "all" ? null : source}, active.signal);
      if (active.signal.aborted) return;
      if (response.project_id !== projectId || response.results.some(chunk => !evidenceBelongsToContent(chunk, contents) ||
        platform !== "all" && chunk.platform !== platform || slot !== "all" && chunk.slot !== slot || source !== "all" && chunk.source_type !== source))
        throw new Error("Returned evidence does not match the selected sources.");
      setResult(response);
    } catch (error) {
      if (!active.signal.aborted) setError(error instanceof Error ? error.message : "Could not search evidence.");
    } finally { if (!active.signal.aborted) setSearching(false); }
  }
  const chunks = result?.results ?? [];
  return <section className="ui-panel evidence-search">
    <div className="evidence-section-heading"><span className="evidence-icon"><Icon name="target" size={21}/></span><div><h2>Retrieve supporting evidence</h2><p className="muted">Search indexed passages by meaning. Read the original sources.</p></div></div>
    <form onSubmit={search} className="evidence-search-form">
      <label htmlFor="evidence-query" className="sr-only">Evidence query</label>
      <div className="evidence-query-row"><input id="evidence-query" value={query} maxLength={1000} placeholder="Search a topic, statement or metric..." onChange={e => {clearSearch(); setQuery(e.target.value);}}/><button type="submit" className="button-primary" disabled={searching || !indexReady || !projectId || !query.trim()}><Icon name="target" size={17}/>{searching ? "Searching..." : "Search evidence"}</button></div>
      <div className="evidence-filters">
        <label>Platform<select aria-label="Platform" value={platform} onChange={e => {clearSearch(); setPlatform(e.target.value as typeof platform);}}><option value="all">All platforms</option>{Array.from(new Set(contents.map(item => item.platform))).map(p => <option key={p} value={p}>{p === "youtube" ? "YouTube" : p === "instagram" ? "Instagram" : "Facebook"}</option>)}</select></label>
        <label>Content<select aria-label="Content" value={slot} onChange={e => {clearSearch(); setSlot(e.target.value as typeof slot);}}><option value="all">Both videos</option><option value="content_1">Content 1</option><option value="content_2">Content 2</option></select></label>
        <label>Evidence type<select aria-label="Evidence type" value={source} onChange={e => {clearSearch(); setSource(e.target.value as typeof source);}}><option value="all">All sources</option>{sources.map(([id,label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      </div>
      <div className="evidence-query-suggestions">{prompts.map(prompt => <button key={prompt} type="button" onClick={() => {clearSearch(); setQuery(prompt);}}>{prompt}</button>)}</div>
    </form>
    {!indexReady && <Notice>Search will be available when indexing completes.</Notice>}
    {error && <Notice tone="error">{error}</Notice>}
    {searching && <p className="evidence-empty" role="status">Finding matching passages...</p>}
    {result && <>
      <div className="evidence-result-heading" aria-live="polite"><h3>{`Results for "${result.query}"`}</h3><span className="muted">{chunks.length} {chunks.length === 1 ? "passage" : "passages"} retrieved</span><button className="source-link" onClick={clearSearch}>Clear results</button></div>
      <RetrievalSummary response={result}/>
      {result.evidence_limitations?.filter(note => !note.startsWith("Relevance scores rank")).map((note,i) => <Notice key={i}>{note}</Notice>)}
      {chunks.length ? <ol className="evidence-results">{chunks.slice(0,visible).map((chunk,i) => <EvidencePassage key={`${chunk.citation_label}-${i}`} chunk={chunk}/>)}</ol> : <p className="evidence-empty">No eligible indexed passages matched this search. Try another phrase or source type.</p>}
      {chunks.length > visible && <button className="button-secondary mt-4" onClick={() => setVisible(n => n + 6)}>Show more passages</button>}
    </>}
  </section>;
}
export function EvidencePassage({chunk}: {chunk: Omit<RetrievedChunk, "score"> & {score?: number}}) {
  const timestamp = evidenceTimestamp(chunk.start_time, chunk.end_time);
  return <li className="evidence-passage" data-content-slot={chunk.slot} data-evidence-id={chunk.chunk_id} data-evidence-revision={chunk.evidence_revision}>
    <div className="evidence-passage-heading">{chunk.match_details && <span className="evidence-rank">#{chunk.match_details.rank}</span>}<span className="evidence-source-label"><PlatformIcon platform={chunk.platform}/>{chunk.slot === "content_1" ? "Content 1" : chunk.slot === "content_2" ? "Content 2" : "Source"}</span><span className="evidence-type">{sources.find(([id]) => id === chunk.source_type)?.[1] ?? chunk.source_type}</span>{timestamp && <span className="evidence-time"><Icon name="clock" size={14}/>{timestamp}</span>}</div>
    {chunk.title && <h4>{chunk.title}</h4>}<blockquote><EvidenceText text={chunk.text} terms={chunk.match_details?.matching_terms ?? []}/></blockquote>
    {chunk.match_details && <div className="evidence-match-details">
      <div className="evidence-match-scores"><span>{chunk.match_details.vector_match ? "Qdrant match" : "Source match"}</span><span>Semantic <strong>{chunk.match_details.semantic_similarity.toFixed(3)}</strong></span><span>Keyword overlap <strong>{chunk.match_details.keyword_overlap.toFixed(3)}</strong></span>{chunk.score != null && <span title="Hybrid ranking score; not confidence">Relevance <strong>{chunk.score.toFixed(3)}</strong></span>}</div>
      <p>{chunk.match_details.matching_terms.length ? `Matching terms: ${chunk.match_details.matching_terms.join(", ")}` : "No exact query-term overlap"}</p>
      <p className="evidence-contributions">{Object.entries(chunk.match_details.contributions).map(([name,value]) => `${name}: ${value.toFixed(3)}`).join(" / ")}</p>
    </div>}<p className="evidence-citation"><Icon name="evidence" size={14}/>{chunk.citation_label}</p>
  </li>;
}

export function EvidenceText({text, terms}: {text: string; terms: string[]}) {
  const matched = new Set(terms.map(term => term.toLowerCase()));
  return <>{text.split(/([a-z0-9]+(?:'[a-z0-9]+)?)/gi).map((part,i) => matched.has(part.toLowerCase()) ? <mark key={i}>{part}</mark> : part)}</>;
}

export function RetrievalSummary({response}: {response: RetrieveResponse}) {
  const details = response.diagnostics;
  if (!details) return <p className="muted text-sm mb-4">Retrieval details are unavailable for this response.</p>;
  const modes: Record<string,string> = {metric_direct: "Metric evidence", hook_focused: "Opening evidence", transcript_deep: "Transcript search", balanced_compare: "Comparative search", strategy_recommendation: "Multi-source search"};
  return <div className="evidence-retrieval-summary" data-retrieval-run={response.retrieval_run_id ?? undefined}>
    <dl><div><dt>Embedding</dt><dd>{details.embedding_model} <span>v{details.embedding_version}</span></dd></div><div><dt>Strategy</dt><dd>{modes[response.retrieval_mode ?? ""] ?? "Hybrid search"}</dd></div><div><dt>Vector candidates</dt><dd>{details.eligible_candidates}</dd></div><div><dt>Search time</dt><dd>{response.retrieval_latency_ms != null ? `${response.retrieval_latency_ms} ms` : "Not recorded"}</dd></div></dl>
    <div className="evidence-retrieval-caption"><span>{details.strategy}</span><span>Content 1: {details.returned_by_slot.content_1 ?? 0} / Content 2: {details.returned_by_slot.content_2 ?? 0}</span></div>
    <p>Relevance ranks passages; it is not confidence or a generated answer.</p>
  </div>;
}
