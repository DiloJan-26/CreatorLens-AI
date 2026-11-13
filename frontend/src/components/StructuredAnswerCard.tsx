import type {
  ComparisonStructuredAnswer,
  MetricStructuredAnswer,
  RecommendationStructuredAnswer,
  StructuredAnswerPayload,
  StructuredEvidenceItem,
  StructuredRecommendationItem,
} from "@/types/project";
import { ResultBanner } from "./ResultBanner";
import { PlatformIcon } from "./PlatformIcon";
import { Icon } from "./ui";

type StructuredAnswerCardProps = {
  payload: StructuredAnswerPayload;
};

export function StructuredAnswerCard({ payload }: StructuredAnswerCardProps) {
  const { answer } = payload;

  return (
    <div
      className="structured-answer grid gap-3"
      data-answer-type={answer.answer_type}
    >
      {payload.fallback_used || payload.warnings.length > 0 ? (
        <StatusNotice payload={payload} />
      ) : null}

      {answer.answer_type === "metric" ? (
        <MetricAnswerCard answer={answer} />
      ) : answer.answer_type === "comparison" ? (
        <ComparisonAnswerCard answer={answer} />
      ) : (
        <RecommendationAnswerCard answer={answer} />
      )}

      {answer.evidence.length > 0 ? (
        <EvidenceSummary evidence={answer.evidence} />
      ) : (
        <p className="notice text-sm">
          No supporting evidence was returned for this answer.
        </p>
      )}
      {answer.answer_type === "recommendation" && answer.hypothetical_draft && <section className="notice text-sm"><strong>Hypothetical draft for an existing supported experiment</strong><p className="mt-2">{answer.hypothetical_draft.text}</p><p className="muted mt-2">Not a measured improvement or performance prediction.</p></section>}
      <Limitations limitations={answer.limitations} />
      {answer.answer_type !== "metric" && (
        <Recommendations recommendations={answer.recommendations} />
      )}
    </div>
  );
}

function MetricAnswerCard({ answer }: { answer: MetricStructuredAnswer }) {
  return (
    <section className="structured-answer-body">
      <CardHeading eyebrow="Confirmed metrics" title="Metric answer" />
      <p className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-800">
        {answer.summary}
      </p>

      {answer.metrics.length > 0 ? (
        <dl className="mt-4 grid gap-2 sm:grid-cols-2">
          {answer.metrics.map((metric, index) => (
            <div
              key={`${metric.slot}-${metric.name}-${index}`}
              className="rounded-md border border-sky-200 bg-white px-3 py-3"
            >
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {slotLabel(metric.slot)} · {metric.name}
              </dt>
              <dd className="mt-1 text-base font-semibold text-slate-950">
                {metric.availability === "confirmed" && metric.value != null
                  ? String(metric.value)
                  : "Unavailable"}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

function ComparisonAnswerCard({
  answer,
}: {
  answer: ComparisonStructuredAnswer;
}) {
  return (
    <section className="structured-answer-body">
      <ResultBanner
        title={answer.decision_status === "incomparable" ? "The selected objective is not comparable" : winnerLabel(answer.winner)}
        winner={answer.winner === "content_1" || answer.winner === "content_2"}
        description="Based on the available metrics and cited evidence."
        detail={<><span className="signal-label">Objective</span><strong>{(answer.objective || "Unspecified").replaceAll("_", " ")}</strong><span className="muted">{(answer.decision_status || answer.evidence_status || "Evidence limited").replaceAll("_", " ")}</span></>}
      />
      <p className="confidence-note">This is an evidence-based decision status, not a probability of correctness.</p>

      {answer.key_reasons.length > 0 ? (
        <CardList title="Why this result?" items={answer.key_reasons} />
      ) : null}
    </section>
  );
}

function RecommendationAnswerCard({
  answer,
}: {
  answer: RecommendationStructuredAnswer;
}) {
  return (
    <section className="structured-answer-body">
      <CardHeading
        eyebrow="Evidence-backed plan"
        title="Recommended improvements"
      />
      <p className="mt-3 text-sm leading-6 text-slate-800">{answer.summary}</p>
    </section>
  );
}

function CardHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-teal-700">
        {eyebrow}
      </p>
      <h3 className="mt-1 text-base font-semibold text-slate-950">{title}</h3>
    </div>
  );
}

function Recommendations({
  recommendations,
}: {
  recommendations: StructuredRecommendationItem[];
}) {
  if (recommendations.length === 0) {
    return null;
  }

  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold text-slate-950">Recommendations</h4>
      <ol className="mt-2 grid gap-2">
        {recommendations.map((item, index) => (
          <li
            key={`${item.recommendation}-${index}`}
            className="rounded-md border border-white/80 bg-white/80 px-3 py-3"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold text-slate-950">
                {index + 1}. {item.recommendation}
              </p>
              <PriorityBadge priority={item.priority} />
            </div>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              {item.rationale}
            </p>
            {item.target_slot && <p className="mt-2 text-sm font-medium">{slotLabel(item.target_slot)}</p>}
            {item.experiment && <p className="mt-2 text-sm"><strong>Experiment: </strong>{item.experiment}</p>}
            {item.limitation && <p className="mt-2 text-sm text-slate-600">{item.limitation}</p>}
            {item.citation_labels.length > 0 && (
              <p className="muted text-xs mt-2">
                Sources: {item.citation_labels.join(" / ")}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: "high" | "medium" | "low" }) {
  const styles = {
    high: "border-rose-200 bg-rose-50 text-rose-700",
    medium: "border-amber-200 bg-amber-50 text-amber-700",
    low: "border-slate-200 bg-slate-50 text-slate-600",
  }[priority];

  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${styles}`}
    >
      {priority}
    </span>
  );
}

function CardList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold text-slate-950">{title}</h4>
      <ol className="reason-list mt-2 text-sm leading-6 text-slate-700">
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
      </ol>
    </div>
  );
}

function Limitations({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-3">
      <h4 className="text-sm font-semibold text-amber-900">Limitations</h4>
      <ul className="mt-2 ml-4 list-disc space-y-1 text-sm leading-6 text-amber-900">
        {limitations.map((limitation, index) => (
          <li key={`${limitation}-${index}`}>{limitation}</li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceSummary({ evidence }: { evidence: StructuredEvidenceItem[] }) {
  return (
    <details open className="evidence-summary">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-teal-700">
        <Icon name="shield" size={16} /> Supporting evidence ({evidence.length})
      </summary>
      <ul className="mt-3 grid gap-2">
        {evidence.map((item, index) => (
          <li key={`${item.citation_label}-${index}`}>
            <div className="evidence-item-heading">
              <Icon
                name={
                  item.source_type === "transcript" ||
                  item.source_type === "hook"
                    ? "transcript"
                    : "evidence"
                }
                size={18}
              />
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  {item.citation_label}
                </p>
                {item.platform && (
                  <span className="platform-label muted mt-1">
                    <PlatformIcon platform={item.platform} size={14} />
                    {item.platform} / {item.source_type || "Evidence"}
                  </span>
                )}
              </div>
            </div>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              {item.claim}
            </p>
            {item.excerpt && (
              <details className="text-xs muted">
                <summary>Source excerpt</summary>
                <p className="whitespace-pre-wrap">{item.excerpt}</p>
              </details>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

function StatusNotice({ payload }: { payload: StructuredAnswerPayload }) {
  const messages = payload.warnings.length
    ? payload.warnings
    : ["A safe evidence-limited answer was returned."];

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
      <p className="font-semibold">
        {payload.fallback_used ? "Evidence-limited response" : "Answer notice"}
      </p>
      <ul className="mt-1 ml-4 list-disc">
        {messages.map((message, index) => (
          <li key={`${message}-${index}`}>{message}</li>
        ))}
      </ul>
    </div>
  );
}

function slotLabel(slot: "content_1" | "content_2"): string {
  return slot === "content_1" ? "Content 1" : "Content 2";
}

function winnerLabel(winner: ComparisonStructuredAnswer["winner"]): string {
  return {
    content_1: "Content 1 has the stronger supported result",
    content_2: "Content 2 has the stronger supported result",
    tie: "The available evidence supports a tie",
    insufficient_evidence: "Not enough evidence to name a winner",
  }[winner];
}
