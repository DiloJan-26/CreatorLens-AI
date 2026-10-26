import type {
  ComparisonStructuredAnswer,
  MetricStructuredAnswer,
  RecommendationStructuredAnswer,
  StructuredAnswerPayload,
  StructuredEvidenceItem,
  StructuredRecommendationItem,
} from "@/types/project";

type StructuredAnswerCardProps = {
  payload: StructuredAnswerPayload;
};

export function StructuredAnswerCard({ payload }: StructuredAnswerCardProps) {
  const { answer } = payload;

  return (
    <div className="mt-3 grid gap-3" data-answer-type={answer.answer_type}>
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
      ) : null}
    </div>
  );
}

function MetricAnswerCard({ answer }: { answer: MetricStructuredAnswer }) {
  return (
    <section className="rounded-lg border border-sky-200 bg-sky-50/70 p-4 dark:border-sky-900 dark:bg-sky-950/30">
      <CardHeading eyebrow="Confirmed metrics" title="Metric answer" />
      <p className="mt-3 whitespace-pre-line text-sm leading-6 text-slate-800 dark:text-slate-100">
        {answer.summary}
      </p>

      {answer.metrics.length > 0 ? (
        <dl className="mt-4 grid gap-2 sm:grid-cols-2">
          {answer.metrics.map((metric, index) => (
            <div
              key={`${metric.slot}-${metric.name}-${index}`}
              className="rounded-md border border-sky-200 bg-white px-3 py-3 dark:border-sky-900 dark:bg-slate-900"
            >
              <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {slotLabel(metric.slot)} · {metric.name}
              </dt>
              <dd className="mt-1 text-base font-semibold text-slate-950 dark:text-slate-50">
                {metric.availability === "confirmed" && metric.value != null
                  ? String(metric.value)
                  : "Unavailable"}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      <Limitations limitations={answer.limitations} />
    </section>
  );
}

function ComparisonAnswerCard({
  answer,
}: {
  answer: ComparisonStructuredAnswer;
}) {
  const confidencePercent = Math.round(answer.confidence * 100);

  return (
    <section className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 dark:border-emerald-900 dark:bg-emerald-950/30">
      <CardHeading eyebrow="Evidence comparison" title={winnerLabel(answer.winner)} />

      <div className="mt-3">
        <div className="flex items-center justify-between gap-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          <span>Confidence</span>
          <span>{confidencePercent}%</span>
        </div>
        <div
          className="mt-2 h-2 overflow-hidden rounded-full bg-emerald-100 dark:bg-emerald-950"
          role="progressbar"
          aria-label="Answer confidence"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={confidencePercent}
        >
          <div
            className="h-full rounded-full bg-emerald-500"
            style={{ width: `${confidencePercent}%` }}
          />
        </div>
      </div>

      {answer.key_reasons.length > 0 ? (
        <CardList title="Why" items={answer.key_reasons} />
      ) : null}
      <Recommendations recommendations={answer.recommendations} />
      <Limitations limitations={answer.limitations} />
    </section>
  );
}

function RecommendationAnswerCard({
  answer,
}: {
  answer: RecommendationStructuredAnswer;
}) {
  return (
    <section className="rounded-lg border border-violet-200 bg-violet-50/70 p-4 dark:border-violet-900 dark:bg-violet-950/30">
      <CardHeading eyebrow="Evidence-backed plan" title="Recommended improvements" />
      <p className="mt-3 text-sm leading-6 text-slate-800 dark:text-slate-100">
        {answer.summary}
      </p>
      <Recommendations recommendations={answer.recommendations} />
      <Limitations limitations={answer.limitations} />
    </section>
  );
}

function CardHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-teal-700 dark:text-teal-300">
        {eyebrow}
      </p>
      <h3 className="mt-1 text-base font-semibold text-slate-950 dark:text-slate-50">
        {title}
      </h3>
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
      <h4 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
        Recommendations
      </h4>
      <ol className="mt-2 grid gap-2">
        {recommendations.map((item, index) => (
          <li
            key={`${item.recommendation}-${index}`}
            className="rounded-md border border-white/80 bg-white/80 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/80"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                {index + 1}. {item.recommendation}
              </p>
              <PriorityBadge priority={item.priority} />
            </div>
            <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {item.rationale}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: "high" | "medium" | "low" }) {
  const styles = {
    high: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200",
    medium:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200",
    low: "border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300",
  }[priority];

  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${styles}`}>
      {priority}
    </span>
  );
}

function CardList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
        {title}
      </h4>
      <ol className="mt-2 ml-5 list-decimal space-y-1 text-sm leading-6 text-slate-700 dark:text-slate-200">
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
    <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-3 dark:border-amber-900 dark:bg-amber-950/50">
      <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-100">
        Limitations
      </h4>
      <ul className="mt-2 ml-4 list-disc space-y-1 text-sm leading-6 text-amber-900 dark:text-amber-100">
        {limitations.map((limitation, index) => (
          <li key={`${limitation}-${index}`}>{limitation}</li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceSummary({ evidence }: { evidence: StructuredEvidenceItem[] }) {
  return (
    <details className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-teal-700 dark:text-teal-300">
        Evidence used ({evidence.length})
      </summary>
      <ul className="mt-3 grid gap-2">
        {evidence.map((item, index) => (
          <li key={`${item.citation_label}-${index}`}>
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              {item.citation_label}
            </p>
            <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {item.claim}
            </p>
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
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100">
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
