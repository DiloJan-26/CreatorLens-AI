import type { ContentItem, ContentPlatform } from "@/types/project";
export function ContentCard({
  item,
  label,
  isPending = false,
}: {
  item: ContentItem | null;
  label: "Content 1" | "Content 2";
  isPending?: boolean;
}) {
  if (!item)
    return (
      <section className="ui-panel">
        <p className="eyebrow">{label}</p>
        <h2>{isPending ? "Processing content..." : "Content unavailable"}</h2>
        <p className="muted mt-3">
          Public metadata has not been returned for this content.
        </p>
      </section>
    );
  const description = item.caption || item.description;
  return (
    <article className="ui-panel content-identity">
      <div className="flex items-start gap-3">
        <span className="content-monogram">{label.slice(-1)}</span>
        <div className="min-w-0">
          <p className="eyebrow">
            {label} / {platformLabel(item.platform)}
          </p>
          <h2 className="text-lg break-words">
            {item.title || "Title unavailable"}
          </h2>
          <p className="muted text-sm mt-2">
            {item.creator ?? item.creator_handle ?? "Creator unavailable"}
          </p>
          <a
            className="source-link"
            href={/^https?:\/\//i.test(item.url) ? item.url : undefined}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open original video
          </a>
        </div>
      </div>
      <p className="muted text-xs mt-3">
        Extracted title / {item.extraction_status.replace(/_/g, " ")}
      </p>
      {item.error_message && (
        <p className="notice notice-error mt-4" role="alert">
          {item.error_message}
        </p>
      )}
      <h3 className="text-sm mt-6 mb-3">Confirmed public metrics</h3>
      <dl className="metric-grid">
        {[
          ["Views", formatNumber(item.views)],
          [
            item.platform === "facebook" ? "Reactions" : "Likes",
            formatNumber(
              item.platform === "facebook" ? item.reactions : item.likes,
            ),
          ],
          ["Comments", formatNumber(item.comments)],
          ["Shares", formatNumber(item.shares)],
          [
            "Followers / subscribers",
            formatNumber(item.follower_count ?? item.subscriber_count),
          ],
          [
            "Engagement rate",
            item.engagement_rate == null
              ? null
              : `${item.engagement_rate.toFixed(2)}%`,
          ],
        ].map(([k, v]) => (
          <Metric key={k} label={k as string} value={v} />
        ))}
      </dl>
      <p className="muted text-xs mt-3">
        Unavailable values are not zero. Engagement rate follows the existing
        calculation and available inputs.
      </p>
      <details className="detail-disclosure mt-5">
        <summary>Content details & provenance</summary>
        <dl className="grid gap-4 sm:grid-cols-2 text-sm my-4">
          <Metric
            label="Duration"
            value={
              item.duration_seconds == null ? null : `${item.duration_seconds}s`
            }
          />
          <Metric label="Published" value={item.upload_date} />
          <Metric label="Transcript" value={transcriptStatus(item)} />
          <Metric
            label="Segments"
            value={formatNumber(item.transcript_segment_count)}
          />
        </dl>
        <p className="text-sm whitespace-pre-wrap mb-4">
          {description || "Description unavailable"}
        </p>
        <p className="muted text-xs mb-4">
          Hashtags:{" "}
          {item.hashtags?.length
            ? item.hashtags.map((x) => `#${x}`).join(" ")
            : "Unavailable"}
        </p>
        {Boolean(item.missing_fields?.length) && (
          <p className="text-sm mb-4">
            Missing fields: {item.missing_fields?.map(fieldLabel).join(", ")}
          </p>
        )}
        <div className="grid gap-3">
          <SourceNote label="Metric source" value={item.metric_source_note} />
          <SourceNote
            label="Transcript source"
            value={item.transcript_source_note}
          />
        </div>
      </details>
    </article>
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
      <dd
        className={`mt-1 break-words text-slate-950 ${value == null ? "unavailable" : ""}`}
      >
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

  const source = item.transcript_source
    ? sourceLabel(item.transcript_source)
    : "Unknown";
  return `${transcriptLanguageStatus(item)} / ${source}`;
}

function sourceLabel(source: string): string {
  if (source === "platform_captions") {
    return "Captions";
  }

  if (source === "deepgram_multilingual") {
    return "Deepgram multilingual";
  }

  if (source === "unavailable") {
    return "Unavailable";
  }

  return source;
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

function transcriptLanguageStatus(item: ContentItem): string {
  const detectedLanguage = item.detected_language;

  if (
    detectedLanguage &&
    !["multi", "multilingual", "auto"].includes(detectedLanguage.toLowerCase())
  ) {
    return `Detected ${languageLabel(detectedLanguage)}`;
  }

  if (item.transcript_language) {
    return `${languageLabel(item.transcript_language)} captions`;
  }

  return "Language not confidently detected";
}

function fieldLabel(value: string): string {
  return value.replace(/_/g, " ");
}
