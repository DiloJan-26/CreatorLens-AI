"use client";

import { useEffect, useState } from "react";
import { getProjectEvidenceChunks } from "@/lib/api";
import type { ContentItem, StoredEvidenceChunk } from "@/types/project";
import { RetrievalTestPanel, evidenceBelongsToContent } from "./RetrievalTestPanel";
import { MetadataAvailabilityPanel } from "./MetadataAvailabilityPanel";
import { Icon, Notice } from "./ui";

export function EvidenceSystemDetails({ projectId, indexReady, contents }: {
  projectId: string; indexReady: boolean; contents: ContentItem[];
}) {
  const [library, setLibrary] = useState<StoredEvidenceChunk[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getProjectEvidenceChunks(projectId, controller.signal).then(data => {
      if (data.project_id !== projectId) throw new Error("Evidence does not match this comparison.");
      if (!controller.signal.aborted) {
        setLibrary(data.chunks.filter(chunk => chunk.project_id === projectId && evidenceBelongsToContent(chunk, contents))); setError(null);
      }
    }).catch(error => {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Could not load evidence.");
    });
    return () => controller.abort();
  }, [projectId, attempt, contents]);
  return <div className="evidence-explorer">
    <div className="evidence-library-status">
      <span className="evidence-icon"><Icon name="evidence" size={22}/></span>
      <div><h2>Evidence library</h2><p className="muted">{library ? `${library.length} stored passages` : error ? "Source passages could not be loaded" : "Loading source passages..."}</p></div>
      <span className={`evidence-status ${indexReady ? "is-ready" : ""}`}>{indexReady ? "Search ready" : "Search not ready"}</span>
    </div>
    {error && <Notice tone="error">{error} <button className="source-link" onClick={() => setAttempt(n => n + 1)}>Retry</button></Notice>}
    <RetrievalTestPanel projectId={projectId} indexReady={indexReady} contents={contents} initialChunks={library ?? []}/>
    <MetadataAvailabilityPanel projectId={projectId} contents={contents}/>
  </div>;
}
