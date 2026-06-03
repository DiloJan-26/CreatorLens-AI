import type { ContentItem, ContentPlatform } from "@/types/project";

type ContentCardProps = {
  item: ContentItem | null;
  label: "Content 1" | "Content 2";
  isPending?: boolean;
};

export function ContentCard({
  item,
  label,
  isPending = false,
}: ContentCardProps) {
  if (!item) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
          {label}
        </p>
        <p className="mt-3 text-sm font-semibold text-slate-950">
          Status: {isPending ? "Pending" : "Unavailable"}
        </p>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Run analysis to extract public metadata and transcript availability.
        </p>
      </section>
    );
  }

  const isFacebook = item.platform === "facebook";
  const description = item.caption || item.description;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            {label} · {platformLabel(item.platform)}
          </p>
          <h2 className="mt-3 text-lg font-semibold text-slate-950">
            {item.title || "Unavailable"}
          </h2>
        </div>
        <span className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium capitalize text-slate-700">
          {item.extraction_status}
        </span>
      </div>

      {item.error_message ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {item.error_message}
        </p>
      ) : null}

      <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
        <p className="text-sm font-medium text-slate-500">
          {item.platform === "instagram" ? "Caption preview" : "Description preview"}
        </p>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
          {description ? truncateText(description, 300) : "Unavailable"}
        </p>
      </div>

      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
        <Metric label="Creator" value={item.creator} />
        <Metric
          label="Follower/subscriber count"
          value={formatNumber(item.follower_count ?? item.subscriber_count)}
        />
        <Metric label="Views" value={formatNumber(item.views)} />
        <Metric label="Likes" value={formatNumber(item.likes)} />
        {isFacebook ? (
          <Metric label="Reactions" value={formatNumber(item.reactions)} />
        ) : null}
        <Metric label="Comments" value={formatNumber(item.comments)} />
        {isFacebook ? (
          <Metric label="Shares" value={formatNumber(item.shares)} />
        ) : null}
        <Metric
          label="Engagement rate"
          value={
            item.engagement_rate == null
              ? null
              : `${item.engagement_rate.toFixed(2)}%`
          }
        />
        <Metric
          label="Duration"
          value={
            item.duration_seconds == null ? null : `${item.duration_seconds}s`
          }
        />
        <Metric label="Upload date" value={item.upload_date} />
        <Metric
          label="Transcript"
          value={transcriptStatus(item)}
        />
        <Metric
          label="Transcript segments"
          value={formatNumber(item.transcript_segment_count)}
        />
      </dl>

      <div className="mt-5">
        <p className="text-sm font-medium text-slate-500">Hashtags</p>
        {item.hashtags && item.hashtags.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {item.hashtags.map((hashtag) => (
              <span
                key={hashtag}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
              >
                #{hashtag}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-1 text-sm text-slate-950">Unavailable</p>
        )}
      </div>

      <div className="mt-5 grid gap-3">
        <SourceNote label="Metric source" value={item.metric_source_note} />
        <SourceNote
          label="Transcript source"
          value={item.transcript_source_note}
        />
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div>
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-950">
        {value ?? "Unavailable"}
      </dd>
    </div>
  );
}

function SourceNote({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-600">
      <span className="font-medium text-slate-700">{label}: </span>
      {value || "Unavailable"}
    </div>
  );
}

function formatNumber(value: number | null | undefined): string | null {
  return value == null ? null : new Intl.NumberFormat("en-US").format(value);
}

function platformLabel(platform: ContentPlatform): string {
  if (platform === "youtube") {
    return "YouTube";
  }

  if (platform === "instagram") {
    return "Instagram";
  }

  return "Facebook";
}

function transcriptStatus(item: ContentItem): string {
  if (!item.transcript_available) {
    return "Unavailable";
  }

  return `Available · ${languageLabel(
    item.detected_language ?? item.transcript_language,
  )}`;
}

function languageLabel(language: string | null | undefined): string {
  if (!language) {
    return "Unknown";
  }

  const normalized = language.toLowerCase();

  if (normalized.startsWith("en")) {
    return "English";
  }

  if (normalized.startsWith("hi")) {
    return "Hindi";
  }

  if (normalized.startsWith("ta")) {
    return "Tamil";
  }

  if (normalized === "multi" || normalized === "multilingual") {
    return "Multilingual";
  }

  return language;
}

function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength).trimEnd()}...`;
}
