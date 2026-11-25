"use client";

import { useEffect, useState } from "react";
import { getMetadataAvailability } from "@/lib/api";
import type { ContentItem, MetadataAvailabilityResponse } from "@/types/project";
import { Icon, Notice } from "./ui";
import { PlatformIcon } from "./PlatformIcon";

const fieldLabel = (field: string) => ({"follower_count/subscriber_count": "Audience size", "likes/reactions": "Likes / reactions", "duration_seconds": "Duration", "upload_date": "Published"}[field] ?? field.replace(/_/g, " "));
export function MetadataAvailabilityPanel({projectId, contents = []}: {projectId: string | null; contents?: ContentItem[]}) {
  const [data, setData] = useState<MetadataAvailabilityResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    if (projectId) getMetadataAvailability(projectId).then(response => {
      if (response.project_id !== projectId) throw new Error("Sources do not match this comparison.");
      if (active) {setData(response); setError(null);}
    }).catch(error => {if (active) setError(error instanceof Error ? error.message : "Could not load source coverage.");});
    return () => {active = false;};
  }, [projectId, attempt]);
  const current = data?.project_id === projectId ? data : null;
  return <section className="ui-panel evidence-coverage">
    <div className="evidence-section-heading"><span className="evidence-icon"><Icon name="shield" size={21}/></span><div><h2>Source coverage</h2><p className="muted">What is available for each video.</p></div></div>
    {error ? <Notice tone="error">{error} <button className="source-link" onClick={() => setAttempt(n => n + 1)}>Retry</button></Notice> : !current && <p className="muted" role="status">Loading source coverage...</p>}
    {current && <div className="evidence-coverage-grid">{current.items.filter(item => contents.some(content => content.slot === item.slot && content.platform === item.platform)).map(item => {
      const content = contents.find(content => content.slot === item.slot);
      const complete = item.available_fields.length > 0 && item.missing_fields.length === 0;
      return <article key={item.slot} className="evidence-coverage-card" data-content-slot={item.slot}>
        <div className="evidence-passage-heading"><span className="evidence-source-label"><PlatformIcon platform={item.platform}/>{item.slot === "content_1" ? "Content 1" : "Content 2"}</span><span className={`evidence-status ${complete ? "is-ready" : ""}`}>{complete ? "All checked fields" : item.missing_fields.length ? "Partial coverage" : "Not assessed"}</span></div>
        <h3>{content?.title ?? "Video source"}</h3>
        <div className="evidence-fields"><p className="evidence-field-label">Available <span>{item.available_fields.length}</span></p><div>{item.available_fields.length ? item.available_fields.map(field => <span className="evidence-field is-available" key={field}><Icon name="check" size={13}/>{fieldLabel(field)}</span>) : <span className="muted">No confirmed fields</span>}</div></div>
        {item.missing_fields.length > 0 && <div className="evidence-fields"><p className="evidence-field-label">Not available <span>{item.missing_fields.length}</span></p><div>{item.missing_fields.map(field => <span className="evidence-field" key={field}>{fieldLabel(field)}</span>)}</div></div>}
        <div className="evidence-provenance">{content?.metric_source_note && <p><strong>Metrics</strong> {content.metric_source_note}</p>}{content?.transcript_source_note && <p><strong>Captions</strong> {content.transcript_source_note}</p>}</div>
        {content?.url && /^https?:\/\//i.test(content.url) && <a className="source-link" href={content.url} target="_blank" rel="noopener noreferrer">Original video <Icon name="external" size={14}/></a>}
      </article>;
    })}</div>}
  </section>;
}
