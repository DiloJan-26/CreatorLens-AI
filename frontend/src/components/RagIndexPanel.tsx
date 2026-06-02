"use client";

import { useState } from "react";

import { indexProject } from "@/lib/api";
import type { IndexProjectResponse } from "@/types/project";

type RagIndexPanelProps = {
  projectId: string | null;
  onIndexed?: (result: IndexProjectResponse) => void;
};

export function RagIndexPanel({ projectId, onIndexed }: RagIndexPanelProps) {
  const [result, setResult] = useState<IndexProjectResponse | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleBuildIndex() {
    if (!projectId) {
      setError("Run extraction before building the search index.");
      return;
    }

    setIsIndexing(true);
    setError(null);

    try {
      const indexResult = await indexProject(projectId);
      setResult(indexResult);
      onIndexed?.(indexResult);

      if (indexResult.status === "failed") {
        setError(indexResult.message ?? "Search index build failed.");
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
            Vector search
          </p>
          <h2 className="mt-2 text-base font-semibold text-slate-950">
            RAG Search Index
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Builds retrieval chunks from transcripts, captions, descriptions,
            hashtags, and metadata, then stores embeddings in Qdrant.
          </p>
        </div>
        <button
          type="button"
          onClick={handleBuildIndex}
          disabled={isIndexing || !projectId}
          className="inline-flex h-10 items-center justify-center rounded-md bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isIndexing ? "Building..." : "Build Search Index"}
        </button>
      </div>

      {isIndexing ? (
        <p className="mt-4 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Building chunks and storing embeddings...
        </p>
      ) : null}

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {result ? (
        <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Metric label="Status" value={result.status} />
          <Metric label="Total chunks" value={result.total_chunks} />
          <Metric label="YouTube chunks" value={result.youtube_chunks} />
          <Metric label="Instagram chunks" value={result.instagram_chunks} />
          <Metric label="Embedding model" value={result.embedding_model} />
          <Metric label="Qdrant collection" value={result.qdrant_collection} />
        </dl>
      ) : null}
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

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not build the search index.";
}
