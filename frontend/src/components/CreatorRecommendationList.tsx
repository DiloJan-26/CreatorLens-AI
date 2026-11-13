import type { ContentInsight, CreatorRecommendationBundle, RecommendationEvidence } from "@/types/project";
import { Icon } from "./ui";

type Props = {
  bundle: CreatorRecommendationBundle;
  contents: (ContentInsight | null | undefined)[];
};

function contentLabel(id: string | null, contents: Props["contents"]) {
  const content = contents.find((item) => item?.content_id === id);
  return content ? `${content.label} · ${content.platform}` : "Comparison evidence";
}

function Evidence({ item, bundle, contents }: { item: RecommendationEvidence } & Props) {
  const owner = contents.find((content) => content?.content_id === item.content_id && content.slot === item.slot && content.platform === item.platform);
  if (!owner || item.project_id !== bundle.project_id) return <p className="text-sm text-amber-800">Evidence ownership could not be verified.</p>;
  const timed = item.start_time != null && item.end_time != null;
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <p className="font-medium">{owner.label} · {item.role === "comparison_context" ? "Comparison context" : "Target evidence"} · {item.source_type.replaceAll("_", " ")}</p>
      {timed && <p className="text-sm text-slate-600">{item.start_time!.toFixed(2)}–{item.end_time!.toFixed(2)}s · Actual segment range</p>}
      {item.excerpt && <blockquote className="mt-2 border-l-2 border-teal-600 pl-3 text-sm leading-6">{item.excerpt}</blockquote>}
      {item.source_type === "metric_snapshot" && <dl className="mt-2 grid gap-1 text-sm">{Object.entries(item.metric_values).filter(([, value]) => value != null).map(([name, value]) => <div key={name}><dt className="inline text-slate-600">{name.replaceAll("_", " ")}: </dt><dd className="inline">{value?.toLocaleString()}</dd></div>)}</dl>}
      {item.source_type === "metric_snapshot" && <p className="mt-2 text-sm text-slate-600">Metric source method: {typeof item.metric_provenance.source_method === "string" ? item.metric_provenance.source_method : "Unavailable"}. These are observed public counts, not retention or sentiment measurements.</p>}
      <p className="mt-2 break-all text-xs text-slate-600">Source: {item.evidence_id}</p>
      <p className="break-all text-xs text-slate-600">Revision: {item.input_revision}</p>
    </div>
  );
}

export function CreatorRecommendationList({ bundle, contents }: Props) {
  return (
    <section className="recommendation-panel rounded-md border border-slate-200 p-4" aria-label="Evidence-grounded creator recommendations">
      <h3 className="flex items-center gap-2 text-base font-semibold"><Icon name="bulb" size={20} /> Evidence-grounded recommendations</h3>
      <p className="mt-2 text-sm text-slate-600">{bundle.policy_version} · Objective: {bundle.selected_objective.replaceAll("_", " ")}</p>
      {bundle.recommendations.length ? <ol className="mt-4 grid gap-4">{bundle.recommendations.map((recommendation) => {
        const target = contents.find((content) => content?.content_id === recommendation.target_content_id && content.slot === recommendation.target_slot && content.platform === recommendation.target_platform);
        if (!target || recommendation.project_id !== bundle.project_id || recommendation.selected_objective !== bundle.selected_objective) return <li key={recommendation.id} className="text-sm text-amber-800">Recommendation withheld because its target could not be verified.</li>;
        return (
          <li key={recommendation.id} data-recommendation-id={recommendation.id} className="rounded-md border border-slate-200 p-4">
            <p className="text-sm font-medium text-teal-800">{target.label} · {target.platform} · {recommendation.priority.label} priority</p>
            <h4 className="mt-1 font-semibold">{recommendation.title}</h4>
            <p className="mt-2 text-sm leading-6"><strong>Supported finding: </strong>{recommendation.detected_weakness}</p><p className="mt-2 text-sm leading-6">{recommendation.observed_signal}</p>
            <p className="mt-3 leading-6"><strong>Try: </strong>{recommendation.recommended_change}</p>
            <p className="mt-2 text-sm leading-6"><strong>Experiment: </strong>{recommendation.experiment}</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">{recommendation.limitation}</p>
            <details className="detail-disclosure mt-3">
              <summary>Supporting evidence and rationale</summary>
              <p className="mt-2 text-sm leading-6">{recommendation.rationale}</p>
              <p className="mt-2 text-sm leading-6">{recommendation.hypothesis}</p>
              <p className="mt-2 text-sm text-slate-600">{recommendation.priority.explanation}</p>
              <p className="mt-2 text-sm text-slate-600">Basis: {recommendation.basis.replaceAll("_", " ")} · Selected decision: {recommendation.comparison.selected_objective_status}</p>
              <div className="mt-3 grid gap-2">{recommendation.evidence.map((item, index) => <Evidence key={`${item.evidence_id}-${index}`} item={item} bundle={bundle} contents={contents} />)}</div>
            </details>
            {recommendation.example && recommendation.example.target_content_id === target.content_id && <details className="detail-disclosure mt-3"><summary>Deterministic draft structure</summary><p className="mt-2 leading-6">{recommendation.example.text}</p><p className="mt-2 text-sm text-slate-600">{recommendation.example.limitation}</p></details>}
          </li>
        );
      })}</ol> : <p className="mt-4 text-sm leading-6">{bundle.status === "unavailable" ? "Recommendation inputs are unavailable." : "No supported actionable weakness was identified from the current evidence. Missing evidence is not treated as a defect."}</p>}
      {bundle.findings.length > 0 && <details className="detail-disclosure mt-4"><summary>Observations and evidence limits ({bundle.findings.length})</summary><ul className="mt-3 grid gap-3">{bundle.findings.map((finding) => <li key={finding.id} className="rounded-md border border-slate-200 p-3 text-sm leading-6"><p className="font-medium">{contentLabel(finding.target_content_id, contents)} · {finding.status.replaceAll("_", " ")}</p><p>{finding.observation}</p>{finding.limitations.length > 0 && <p className="text-slate-600">{finding.limitations.join(" ")}</p>}{finding.missing_evidence.length > 0 && <p className="text-slate-600">Missing: {finding.missing_evidence.join("; ")}</p>}{finding.evidence.length > 0 && <details className="mt-2"><summary>Evidence references</summary><div className="mt-2 grid gap-2">{finding.evidence.map((item, index) => <Evidence key={`${item.evidence_id}-${index}`} item={item} bundle={bundle} contents={contents} />)}</div></details>}</li>)}</ul></details>}
      <p className="mt-3 text-sm leading-6 text-slate-600">{bundle.limitations.join(" ")}</p>
    </section>
  );
}
