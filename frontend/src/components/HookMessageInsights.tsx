import Link from "next/link";
import type {HookMessageAssessment, ObservedContent, ObservedRecommendation} from "@/types/project";
import {Icon} from "./ui";

export function HookMessageInsights({contents,recommendations}: {
  contents: ObservedContent[]; recommendations: ObservedRecommendation[];
}) {
  return <section aria-labelledby="hook-message-title">
    <div className="insight-section-heading"><Icon name="bulb" size={23}/><div>
      <h2 id="hook-message-title">Hook &amp; Message Insights</h2>
      <p>How each video introduces its topic and viewer takeaway.</p>
    </div></div>
    <div className="video-insight-grid">{contents.map(content => <HookMessageCard key={content.content_id} content={content} recommendations={recommendations.filter(r => r.target_content_id===content.content_id && r.target_slot===content.slot)}/>)}</div>
  </section>;
}

function HookMessageCard({content,recommendations}: {content:ObservedContent;recommendations:ObservedRecommendation[]}) {
  const analysis=content.hook_message;
  const assessments=analysis?.assessments ?? [];
  // Compatibility data can still be read, but is not relabeled as the new policy.
  const findings=assessments.filter(a => a.status!=="not_assessable" && a.rule_id!=="topic_position" && !(a.rule_id==="generic_intro" && !a.matched));
  const groups=Array.from(new Set(findings.flatMap(a => a.evidence_ids))).map(id => ({
    id,ref:content.evidence.find(e => e.evidence_id===id && e.content_id===content.content_id && e.slot===content.slot),
    findings:findings.filter(a => a.evidence_ids.includes(id)),
  })).filter(group => group.ref);
  const scope=analysis?.opening_scope;
  const position=assessments.find(a => a.rule_id==="topic_position" && a.status==="detected");
  const unknownOpening=assessments.find(a => a.rule_id==="opening_topic" && a.status==="not_assessable");
  return <article className="ui-panel video-insight-card hook-message-card" data-content-slot={content.slot}>
    <div className="hook-card-top"><p className="eyebrow">Content {content.slot.slice(-1)}</p><span className="hook-status">{analysis?.status==="assessed"?"Reviewed":analysis?.status==="partial"?"Partial review":"Evidence limited"}</span></div>
    <h3>{content.title ?? "Video"}</h3>
    {scope && scope.kind!=="unavailable" && <p className="hook-scope"><Icon name={scope.kind==="timed"?"clock":"transcript"} size={14}/>{scope.label}{scope.coverage==="partial"?" / Partial opening":scope.kind==="word_passage"?" / No timing claim":""}</p>}
    {unknownOpening && <p className="hook-coverage-note">{unknownOpening.observation}</p>}
    {groups.map(group => {
      const excerpt=group.findings.find(a => a.excerpt)?.excerpt;
      const excerptOwner=group.findings.find(a => a.excerpt);
      const experiments=recommendations.filter(r => r.evidence_ids.includes(group.id));
      return <div className="hook-source-group" key={group.id}>
        <p className="hook-source-label">{group.ref?.source_type==="description"?"Description":"Opening passage"}</p>
        <ul className="hook-findings">{group.findings.map(finding => <li key={finding.id}>
          <div className="hook-finding-heading"><Icon name={finding.status==="detected"?"check":"evidence"} size={15}/><h4>{finding.title}</h4><span>{finding.status==="detected"?"Detected":"Not detected in scope"}</span></div>
          <p>{finding.observation}</p>
          {finding.rule_id==="opening_topic" && position && <p className="hook-position">{position.observation}{segmentRange(position)}</p>}
        </li>)}</ul>
        {excerpt && <div className="hook-excerpt"><p>Evidence</p><blockquote>{excerptOwner?.excerpt_start?"…":""}{excerpt}{excerptOwner?.excerpt_end!=null && group.ref && excerptOwner.excerpt_end<group.ref.text.length?"…":""}</blockquote><span>{group.ref?.start_time!=null && group.ref.end_time!=null?`${group.ref.start_time.toFixed(1)}-${group.ref.end_time.toFixed(1)}s / `:""}{group.ref?.source_type==="description"?group.findings[0].scope.label:"Caption evidence"}</span></div>}
        {experiments.map(r => <div className="hook-experiment" key={r.id} data-recommendation-id={r.id}>
          <div><Icon name="bulb" size={15}/><strong>Suggested experiment</strong><span>{r.priority.label} priority</span></div>
          <p>{r.experiment}</p><small>Optional wording test; no performance outcome is established.</small>
        </div>)}
        <Link className="source-link hook-source-link" href="/analyze#evidence"><Icon name="evidence" size={14}/>View source evidence</Link>
      </div>;
    })}
    {!analysis && <p className="hook-coverage-note">Refresh this comparison to load Hook &amp; Message Insights.</p>}
    {analysis && !groups.length && !unknownOpening && <p className="hook-coverage-note">No source-supported wording finding is available.</p>}
    {analysis?.limitations.filter(note => !note.startsWith("Partial or gapped")).slice(0,2).map(note => <p className="hook-footnote" key={note}>{note}</p>)}
  </article>;
}
function segmentRange(finding:HookMessageAssessment) {
  const range=finding.measured.segment_range;
  if (!Array.isArray(range)||range.length!==2||range.some(n=>typeof n!=="number"||!Number.isFinite(n))) return "";
  return ` Matching segment: ${range[0]}-${range[1]}s.`;
}
