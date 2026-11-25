"use client";

import { useEffect, useRef, useState } from "react";
import { retrieveProjectChunks } from "@/lib/api";
import type { ContentItem, ContentPlatform, ContentSlot, RetrievedChunk, RetrieveProjectChunksRequest, StoredEvidenceChunk } from "@/types/project";
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

export function RetrievalTestPanel({ projectId, indexReady, contents = [], initialChunks = [] }: {
  projectId: string | null; indexReady: boolean; contents?: ContentItem[]; initialChunks?: StoredEvidenceChunk[];
}) {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<ContentPlatform | "all">("all");
  const [slot, setSlot] = useState<ContentSlot | "all">("all");
  const [source, setSource] = useState<Source | "all">("all");
  const [result, setResult] = useState<{query: string; chunks: RetrievedChunk[]; limitations: string[]} | null>(null);
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
      const response = await retrieveProjectChunks(projectId, {query: query.trim(), top_k: 8,
        platform: platform === "all" ? null : platform, slot: slot === "all" ? null : slot, source_type: source === "all" ? null : source}, active.signal);
      if (active.signal.aborted) return;
      if (response.project_id !== projectId || response.results.some(chunk => !evidenceBelongsToContent(chunk, contents) ||
        platform !== "all" && chunk.platform !== platform || slot !== "all" && chunk.slot !== slot || source !== "all" && chunk.source_type !== source))
        throw new Error("Returned evidence does not match the selected sources.");
      setResult({query: response.query, chunks: response.results, limitations: response.evidence_limitations ?? []});
    } catch (error) {
      if (!active.signal.aborted) setError(error instanceof Error ? error.message : "Could not search evidence.");
    } finally { if (!active.signal.aborted) setSearching(false); }
  }
  const chunks = result ? result.chunks : initialChunks.filter(chunk => evidenceBelongsToContent(chunk, contents) &&
    (platform === "all" || chunk.platform === platform) && (slot === "all" || chunk.slot === slot) && (source === "all" || chunk.source_type === source));
  return <section className="ui-panel evidence-search">
    <div className="evidence-section-heading"><span className="evidence-icon"><Icon name="target" size={21}/></span><div><h2>Search supporting evidence</h2><p className="muted">Find the source behind a metric, opening or claim.</p></div></div>
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
    {!indexReady && <Notice>Stored passages remain available. Search will be available when indexing completes.</Notice>}
    {error && <Notice tone="error">{error}</Notice>}
    <div className="evidence-result-heading" aria-live="polite"><h3>{result ? `Results for \"${result.query}\"` : "Source passages"}</h3><span className="muted">{chunks.length} passages{result ? " retrieved" : " available"}</span>{result && <button className="source-link" onClick={clearSearch}>Browse all sources</button>}</div>
    {result?.limitations.map((note,i) => <Notice key={i}>{note}</Notice>)}
    {chunks.length ? <ol className="evidence-results">{chunks.slice(0,visible).map((chunk,i) => <EvidencePassage key={`${chunk.citation_label}-${i}`} chunk={chunk}/>)}</ol> : <p className="evidence-empty">{searching ? "Finding matching passages..." : result ? "No evidence matched this search. Try another phrase or source type." : "No stored passages match these filters."}</p>}
    {chunks.length > visible && <button className="button-secondary mt-4" onClick={() => setVisible(n => n + 6)}>Show more passages</button>}
  </section>;
}
export function EvidencePassage({chunk}: {chunk: Omit<RetrievedChunk, "score">}) {
  const timestamp = evidenceTimestamp(chunk.start_time, chunk.end_time);
  return <li className="evidence-passage" data-content-slot={chunk.slot}>
    <div className="evidence-passage-heading"><span className="evidence-source-label"><PlatformIcon platform={chunk.platform}/>{chunk.slot === "content_1" ? "Content 1" : chunk.slot === "content_2" ? "Content 2" : "Source"}</span><span className="evidence-type">{sources.find(([id]) => id === chunk.source_type)?.[1] ?? chunk.source_type}</span>{timestamp && <span className="evidence-time"><Icon name="clock" size={14}/>{timestamp}</span>}</div>
    {chunk.title && <h4>{chunk.title}</h4>}<blockquote>{chunk.text}</blockquote><p className="evidence-citation"><Icon name="evidence" size={14}/>{chunk.citation_label}</p>
  </li>;
}
