import type { ContentInsight } from "@/types/project";

type InsightScoreCardProps = {
  content: ContentInsight;
};

export function InsightScoreCard({ content }: InsightScoreCardProps) {
  return (
    <article className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            {content.label} - {platformLabel(content.platform)}
          </p>
          <h3 className="mt-2 text-base font-semibold text-slate-950">
            {content.title || "Untitled content"}
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            Creator: {content.creator || "Unavailable"}
          </p>
        </div>
        <div className="w-fit rounded-md border border-teal-200 bg-white px-3 py-2 text-right">
          <p className="text-xs font-medium text-slate-500">
            Creator Insight Score
          </p>
          <p className="mt-1 text-2xl font-semibold text-slate-950">
            {content.scores.overall_score}/10
          </p>
        </div>
      </div>

      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
        <Metric label="Hook type" value={hookTypeLabel(content.hook_analysis.hook_type)} />
        <Metric
          label="Hook score"
          value={`${content.hook_analysis.hook_score}/10`}
        />
        <Metric
          label="Metadata completeness"
          value={`${content.scores.metadata_completeness}/10`}
        />
        <Metric
          label="Engagement confidence"
          value={`${content.scores.engagement_confidence}/10`}
        />
        <Metric
          label="Caption strength"
          value={`${content.scores.caption_strength}/10`}
        />
        <Metric
          label="CTA strength"
          value={`${content.scores.cta_strength}/10`}
        />
      </dl>

      <p className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-600">
        <span className="font-medium text-slate-700">Metadata Confidence: </span>
        {content.metric_confidence_note}
      </p>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <FieldList title="Strengths" fields={content.strengths} />
        <FieldList title="Weaknesses" fields={content.weaknesses} />
      </div>

      <FieldList
        title="Missing metadata"
        fields={content.missing_metadata}
        emptyLabel="No missing metadata in checked fields"
      />

      {content.top_improvement ? (
        <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm leading-6 text-amber-900">
          <span className="font-medium">Top improvement: </span>
          {content.top_improvement}
        </p>
      ) : null}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-950">{value}</dd>
    </div>
  );
}

function FieldList({
  title,
  fields,
  emptyLabel = "Unavailable",
}: {
  title: string;
  fields: string[];
  emptyLabel?: string;
}) {
  return (
    <div className="mt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </p>
      {fields.length > 0 ? (
        <ul className="mt-2 grid gap-2">
          {fields.map((field) => (
            <li
              key={field}
              className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-700"
            >
              {fieldLabel(field)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-600">{emptyLabel}</p>
      )}
    </div>
  );
}

function platformLabel(platform: string): string {
  if (platform === "youtube") {
    return "YouTube";
  }

  if (platform === "instagram") {
    return "Instagram";
  }

  if (platform === "facebook") {
    return "Facebook";
  }

  return platform;
}

function hookTypeLabel(value: string): string {
  return fieldLabel(value);
}

function fieldLabel(value: string): string {
  return value.replace(/_/g, " ");
}
