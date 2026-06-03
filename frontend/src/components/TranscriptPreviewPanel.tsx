"use client";

import { useState } from "react";

import { getTranscriptPreview } from "@/lib/api";
import type {
  ContentItem,
  TranscriptPreviewResponse,
  TranscriptSegment,
} from "@/types/project";

type TranscriptPreviewPanelProps = {
  projectId: string | null;
  item: ContentItem | null;
  label: "Content 1" | "Content 2";
};

export function TranscriptPreviewPanel({
  projectId,
  item,
  label,
}: TranscriptPreviewPanelProps) {
  const [preview, setPreview] = useState<TranscriptPreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLoadPreview() {
    if (!projectId) {
      setError("Run extraction before loading a transcript preview.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const transcriptPreview = await getTranscriptPreview(
        projectId,
        {
          slot: item?.slot ?? null,
          platform: item?.platform ?? null,
        },
        5,
      );
      setPreview(transcriptPreview);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
      setPreview(null);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            {label} {item ? `· ${platformLabel(item.platform)}` : ""}
          </p>
          <h2 className="mt-2 text-base font-semibold text-slate-950">
            Transcript Preview
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Transcript preview for indexing readiness.
          </p>
        </div>
        <button
          type="button"
          onClick={handleLoadPreview}
          disabled={isLoading || !projectId || !item}
          className="inline-flex h-10 items-center justify-center rounded-md bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isLoading ? "Loading..." : "Load transcript preview"}
        </button>
      </div>

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {preview ? (
        <div className="mt-4">
          <p className="text-sm text-slate-600">
            Segments: {preview.transcript_segment_count}
          </p>
          {!preview.transcript_available || preview.segments.length === 0 ? (
            <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
              Transcript unavailable for this content item.
            </p>
          ) : (
            <ol className="mt-3 grid gap-3">
              {preview.segments.map((segment) => (
                <li
                  key={segment.segment_index}
                  className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-700"
                >
                  <SegmentTimestamp segment={segment} />
                  {segment.text}
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </section>
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

function SegmentTimestamp({ segment }: { segment: TranscriptSegment }) {
  if (segment.start_time == null || segment.end_time == null) {
    return null;
  }

  return (
    <span className="mr-2 font-medium text-slate-500">
      [{formatSeconds(segment.start_time)} - {formatSeconds(segment.end_time)}]
    </span>
  );
}

function formatSeconds(value: number): string {
  return `${value.toFixed(2)}s`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not load transcript preview.";
}
