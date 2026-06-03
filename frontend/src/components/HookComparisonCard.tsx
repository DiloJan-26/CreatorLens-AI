import type { ComparisonInsight, ContentInsight } from "@/types/project";

type HookComparisonCardProps = {
  content1: ContentInsight | null;
  content2: ContentInsight | null;
  comparison: ComparisonInsight;
};

export function HookComparisonCard({
  content1,
  content2,
  comparison,
}: HookComparisonCardProps) {
  return (
    <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Hook Analysis
          </p>
          <h3 className="mt-2 text-base font-semibold text-slate-950">
            Hook comparison
          </h3>
        </div>
        <span className="w-fit rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700">
          Winner: {comparison.hook_winner || "Unavailable"}
        </span>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <HookDetail label="Content 1" content={content1} />
        <HookDetail label="Content 2" content={content2} />
      </div>

      <p className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-600">
        {comparison.main_reason}
      </p>
    </section>
  );
}

function HookDetail({
  label,
  content,
}: {
  label: "Content 1" | "Content 2";
  content: ContentInsight | null;
}) {
  if (!content) {
    return (
      <article className="rounded-md border border-slate-200 bg-white px-3 py-3">
        <h4 className="text-sm font-semibold text-slate-950">{label}</h4>
        <p className="mt-2 text-sm text-slate-600">Hook Analysis unavailable.</p>
      </article>
    );
  }

  return (
    <article className="rounded-md border border-slate-200 bg-white px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold text-slate-950">
          {label} · {platformLabel(content.platform)}
        </h4>
        <span className="rounded-md border border-slate-200 px-2 py-1 text-xs font-medium text-slate-700">
          {content.hook_analysis.hook_score}/10
        </span>
      </div>
      <p className="mt-2 text-sm font-medium text-slate-600">
        Type: {fieldLabel(content.hook_analysis.hook_type)}
      </p>
      <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700">
        {content.hook_analysis.hook_text || "Hook text unavailable."}
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-600">
        {content.hook_analysis.clarity_reason}
      </p>
    </article>
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

function fieldLabel(value: string): string {
  return value.replace(/_/g, " ");
}
