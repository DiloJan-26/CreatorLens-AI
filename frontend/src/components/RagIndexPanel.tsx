"use client";

import { useState } from "react";

import { indexProject } from "@/lib/api";
import type { ContentChunkCount, IndexProjectResponse } from "@/types/project";

type RagIndexPanelProps = {
  projectId: string | null;
  initialResult?: IndexProjectResponse | null;
  onIndexed?: (result: IndexProjectResponse) => void;
};

export function RagIndexPanel({
  projectId,
  initialResult = null,
  onIndexed,
}: RagIndexPanelProps) {
  const [result, setResult] = useState<IndexProjectResponse | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const visibleResult = result ?? initialResult;

  async function handleBuildIndex() {
    if (!projectId) {
      setError("Analyze content before rebuilding the evidence index.");
      return;
    }

    setIsIndexing(true);
    setError(null);

    try {
      const indexResult = await indexProject(projectId);
      setResult(indexResult);
      onIndexed?.(indexResult);

      if (indexResult.status === "failed") {
        setError(indexResult.message ?? "Evidence index rebuild failed.");
      }
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
      setResult(null);
    } finally {
      setIsIndexing(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Evidence Index
          </p>
          <h2 className="mt-2 text-base font-semibold text-slate-950">
            Evidence Index Status
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            The normal analysis flow builds cited evidence automatically from
            transcripts, captions, descriptions, hashtags, and metadata.
          </p>
        </div>
        <button
          type="button"
          onClick={handleBuildIndex}
          disabled={isIndexing || !projectId}
          className="inline-flex h-10 items-center justify-center rounded-md bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isIndexing ? "Rebuilding..." : "Rebuild Evidence Index"}
        </button>
      </div>

      {isIndexing ? (
        <p className="mt-4 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Rebuilding evidence chunks and storing embeddings...
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {visibleResult ? (
        <div className="mt-5 grid gap-5">
          <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Evidence index" value={statusLabel(visibleResult.status)} />
            <Metric label="Total chunks" value={visibleResult.total_chunks} />
            <Metric label="Embedding model" value={visibleResult.embedding_model} />
            <Metric label="Qdrant collection" value={visibleResult.qdrant_collection} />
          </dl>

          <ChunkCountSection
            title="Content chunks"
            items={contentChunkCounts(visibleResult)}
          />

          <ChunkCountSection
            title="Platform chunks"
            items={platformChunkCounts(visibleResult)}
          />
        </div>
      ) : (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-600">
          Evidence index details appear after analysis. If indexing fails, you
          can retry from this advanced section.
        </p>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="font-medium text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-950">{value}</dd>
    </div>
  );
}

function ChunkCountSection({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; chunks: number }>;
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </h3>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <Metric key={item.label} label={item.label} value={item.chunks} />
        ))}
      </dl>
    </section>
  );
}

function contentChunkCounts(
  result: IndexProjectResponse,
): Array<{ label: string; chunks: number }> {
  const counts = result.content_chunk_counts ?? [];

  if (counts.length > 0) {
    return counts.map((item) => ({
      label: contentChunkLabel(item),
      chunks: item.chunks,
    }));
  }

  if (result.chunks_by_slot && Object.keys(result.chunks_by_slot).length > 0) {
    return Object.entries(result.chunks_by_slot).map(([slot, chunks]) => ({
      label: slotLabel(slot),
      chunks,
    }));
  }

  return [];
}

function platformChunkCounts(
  result: IndexProjectResponse,
): Array<{ label: string; chunks: number }> {
  if (
    result.chunks_by_platform &&
    Object.keys(result.chunks_by_platform).length > 0
  ) {
    return Object.entries(result.chunks_by_platform).map(
      ([platform, chunks]) => ({
        label: platformLabel(platform),
        chunks,
      }),
    );
  }

  return [
    { label: "YouTube", chunks: result.youtube_chunks },
    { label: "Instagram", chunks: result.instagram_chunks },
    { label: "Facebook", chunks: result.facebook_chunks ?? 0 },
  ].filter((item) => item.chunks > 0);
}

function contentChunkLabel(item: ContentChunkCount): string {
  const label = item.label || slotLabel(item.slot ?? "");
  return `${label} - ${platformLabel(item.platform)}`;
}

function slotLabel(slot: string): string {
  if (slot === "content_1") {
    return "Content 1";
  }

  if (slot === "content_2") {
    return "Content 2";
  }

  return "Content";
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

function statusLabel(status: string): string {
  return status === "indexed" ? "Ready" : "Failed";
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not rebuild the evidence index.";
}
