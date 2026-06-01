import type { VideoMetadata } from "@/types/project";

type VideoInsightCardProps = {
  platform: "youtube" | "instagram";
  metadata: VideoMetadata | null;
  isPending?: boolean;
};

export function VideoInsightCard({
  platform,
  metadata,
  isPending = false,
}: VideoInsightCardProps) {
  const platformTitle = platform === "youtube" ? "YouTube" : "Instagram";

  if (!metadata) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
          {platformTitle}
        </p>
        <p className="mt-3 text-sm font-semibold text-slate-950">
          Status: {isPending || platform === "instagram" ? "Pending" : "Unavailable"}
        </p>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          {platform === "instagram"
            ? "Instagram extraction is prepared in the normalized schema and will be implemented next."
            : "Run analysis to extract YouTube metadata and transcript availability."}
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            {platformTitle}
          </p>
          <h2 className="mt-3 text-lg font-semibold text-slate-950">
            {metadata.title || "Unavailable"}
          </h2>
        </div>
        <span className="rounded-md border border-slate-200 px-2.5 py-1 text-xs font-medium capitalize text-slate-700">
          {metadata.extraction_status}
        </span>
      </div>

      {metadata.error_message ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {metadata.error_message}
        </p>
      ) : null}

      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
        <Metric label="Creator" value={metadata.creator} />
        <Metric label="Views" value={formatNumber(metadata.views)} />
        <Metric label="Likes" value={formatNumber(metadata.likes)} />
        <Metric label="Comments" value={formatNumber(metadata.comments)} />
        <Metric
          label="Engagement rate"
          value={
            metadata.engagement_rate == null
              ? "Not enough public data"
              : `${metadata.engagement_rate}%`
          }
        />
        <Metric
          label="Duration"
          value={
            metadata.duration_seconds == null
              ? null
              : `${metadata.duration_seconds}s`
          }
        />
        <Metric label="Upload date" value={metadata.upload_date} />
        <Metric
          label="Transcript"
          value={metadata.transcript_available ? "Available" : "Unavailable"}
        />
        <Metric
          label="Transcript segments"
          value={formatNumber(metadata.transcript_segment_count)}
        />
      </dl>

      {metadata.hashtags && metadata.hashtags.length > 0 ? (
        <div className="mt-5">
          <p className="text-sm font-medium text-slate-500">Hashtags</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {metadata.hashtags.map((hashtag) => (
              <span
                key={hashtag}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
              >
                #{hashtag}
              </span>
            ))}
          </div>
        </div>
      ) : null}
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
      <dd className="mt-1 text-slate-950">{value ?? "Unavailable"}</dd>
    </div>
  );
}

function formatNumber(value: number | null | undefined): string | null {
  return value == null ? null : new Intl.NumberFormat("en-US").format(value);
}
