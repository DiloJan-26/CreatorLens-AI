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
          <div className="grid gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600 sm:grid-cols-4">
            <PreviewMetric
              label="Source"
              value={transcriptSourceLabel(preview.transcript_source)}
            />
            <PreviewMetric
              label="Transcript Language"
              value={languageLabel(
                preview.detected_language ?? preview.transcript_language,
              )}
            />
            <PreviewMetric
              label="Confidence"
              value={confidenceLabel(preview.language_confidence)}
            />
            <PreviewMetric
              label="Segments"
              value={String(preview.transcript_segment_count)}
            />
          </div>
          {preview.transcript_source_note ? (
            <p className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-600">
              {preview.transcript_source_note}
            </p>
          ) : null}
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

function PreviewMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-slate-950">{value}</p>
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

function transcriptSourceLabel(source: string | null | undefined): string {
  if (source === "platform_captions") {
    return "Captions";
  }

  if (source === "deepgram_multilingual") {
    return "Deepgram multilingual";
  }

  if (source === "unavailable") {
    return "Unavailable";
  }

  return "Unknown";
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

function confidenceLabel(confidence: number | null | undefined): string {
  if (confidence == null) {
    return "Unknown";
  }

  const percent = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(percent)}%`;
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
