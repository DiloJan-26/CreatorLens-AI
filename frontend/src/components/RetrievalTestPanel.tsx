"use client";

import { useState } from "react";

import { retrieveProjectChunks } from "@/lib/api";
import type {
  ContentPlatform,
  ContentSlot,
  RetrievedChunk,
  RetrieveResponse,
} from "@/types/project";

type PlatformFilter = ContentPlatform | null;
type SlotFilter = ContentSlot | null;
type SourceTypeFilter = "metadata" | "description" | "hook" | "transcript" | null;

type SuggestedQuery = {
  label: string;
  query: string;
  platform: PlatformFilter;
  slot: SlotFilter;
  sourceType: SourceTypeFilter;
};

const SUGGESTED_QUERIES: SuggestedQuery[] = [
  {
    label: "Compare hooks in the first 5 seconds",
    query: "Compare the hooks in the first 5 seconds",
    platform: null,
    slot: null,
    sourceType: "hook",
  },
  {
    label: "Which content has stronger confirmed engagement?",
    query: "Which content has stronger confirmed engagement?",
    platform: null,
    slot: null,
    sourceType: null,
  },
  {
    label: "What metadata is missing?",
    query: "What metadata is missing?",
    platform: null,
    slot: null,
    sourceType: "metadata",
  },
  {
    label: "Suggest improvements for Content 2 based on Content 1",
    query: "Suggest improvements for Content 2 based on Content 1",
    platform: null,
    slot: null,
    sourceType: null,
  },
];

type RetrievalTestPanelProps = {
  projectId: string | null;
  indexReady: boolean;
};

export function RetrievalTestPanel({
  projectId,
  indexReady,
}: RetrievalTestPanelProps) {
  const [query, setQuery] = useState(SUGGESTED_QUERIES[0].query);
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>(
    SUGGESTED_QUERIES[0].platform,
  );
  const [slotFilter, setSlotFilter] = useState<SlotFilter>(
    SUGGESTED_QUERIES[0].slot,
  );
  const [sourceTypeFilter, setSourceTypeFilter] = useState<SourceTypeFilter>(
    SUGGESTED_QUERIES[0].sourceType,
  );
  const [result, setResult] = useState<RetrieveResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    if (!projectId) {
      setError("Run extraction before testing retrieval.");
      return;
    }

    if (!indexReady) {
      setError("Build the search index before testing retrieval.");
      return;
    }

    if (!query.trim()) {
      setError("Enter a retrieval query.");
      return;
    }

    setIsSearching(true);
    setError(null);

    try {
      const retrievalResult = await retrieveProjectChunks(projectId, {
        query: query.trim(),
        top_k: 6,
        platform: platformFilter,
        slot: slotFilter,
        source_type: sourceTypeFilter,
      });
      setResult(retrievalResult);
    } catch (caughtError) {
      setError(getErrorMessage(caughtError));
      setResult(null);
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Source retrieval
          </p>
          <h2 className="mt-2 text-base font-semibold text-slate-950">
            Test Source Retrieval
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Semantic source retrieval test for indexed YouTube, Instagram, and
            Facebook chunks. This panel verifies the sources that will ground
            the final chat answers.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-3">
        <label className="text-sm font-medium text-slate-900">
          Retrieval query
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="mt-2 h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm font-medium text-slate-900">
            Platform
            <select
              value={platformFilter ?? "all"}
              onChange={(event) =>
                setPlatformFilter(
                  event.target.value === "all"
                    ? null
                    : (event.target.value as Exclude<PlatformFilter, null>),
                )
              }
              className="mt-2 h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
            >
              <option value="all">All platforms</option>
              <option value="youtube">YouTube</option>
              <option value="instagram">Instagram</option>
              <option value="facebook">Facebook</option>
            </select>
          </label>

          <label className="text-sm font-medium text-slate-900">
            Content
            <select
              value={slotFilter ?? "all"}
              onChange={(event) =>
                setSlotFilter(
                  event.target.value === "all"
                    ? null
                    : (event.target.value as Exclude<SlotFilter, null>),
                )
              }
              className="mt-2 h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
            >
              <option value="all">Both contents</option>
              <option value="content_1">Content 1</option>
              <option value="content_2">Content 2</option>
            </select>
          </label>

          <label className="text-sm font-medium text-slate-900">
            Source type
            <select
              value={sourceTypeFilter ?? "all"}
              onChange={(event) =>
                setSourceTypeFilter(
                  event.target.value === "all"
                    ? null
                    : (event.target.value as Exclude<SourceTypeFilter, null>),
                )
              }
              className="mt-2 h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
            >
              <option value="all">All sources</option>
              <option value="metadata">Metadata</option>
              <option value="description">Description/Caption</option>
              <option value="hook">Hook</option>
              <option value="transcript">Transcript</option>
            </select>
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          {SUGGESTED_QUERIES.map((suggestedQuery) => (
            <button
              key={suggestedQuery.label}
              type="button"
              onClick={() => {
                setQuery(suggestedQuery.query);
                setPlatformFilter(suggestedQuery.platform);
                setSlotFilter(suggestedQuery.slot);
                setSourceTypeFilter(suggestedQuery.sourceType);
              }}
              className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-medium text-slate-700 transition hover:border-teal-300 hover:bg-teal-50"
            >
              {suggestedQuery.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={handleSearch}
          disabled={isSearching || !projectId || !indexReady}
          className="inline-flex h-10 w-fit items-center justify-center rounded-md bg-teal-700 px-4 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        >
          {isSearching ? "Searching..." : "Search Chunks"}
        </button>
      </div>

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-5">
          <p className="text-sm leading-6 text-slate-600">
            Results: {result.total_results}
            <span className="block">
              Filters: platform ={" "}
              {platformFilterLabel(result.applied_platform ?? null)}, source ={" "}
              {sourceTypeLabel(result.applied_source_type ?? null)}, content ={" "}
              {slotFilterLabel(result.applied_slot ?? null)}
            </span>
          </p>
          {result.results.length === 0 ? (
            <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
              No indexed chunks matched this query.
            </p>
          ) : (
            <ol className="mt-3 grid gap-3">
              {result.results.map((chunk, index) => (
                <RetrievedChunkCard
                  key={`${chunk.citation_label}-${index}`}
                  chunk={chunk}
                />
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </section>
  );
}

function RetrievedChunkCard({ chunk }: { chunk: RetrievedChunk }) {
  return (
    <li className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-slate-950">
            {chunk.citation_label}
          </p>
          <p className="mt-1 text-xs font-medium uppercase text-slate-500">
            {platformLabel(chunk.platform)} / {sourceTypeLabel(chunk.source_type)}
            {chunk.slot ? ` / ${slotFilterLabel(chunk.slot as SlotFilter)}` : ""}
          </p>
        </div>
        <span className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700">
          {chunk.score.toFixed(4)}
        </span>
      </div>
      <p className="mt-3 line-clamp-5 whitespace-pre-wrap text-sm leading-6 text-slate-700">
        {chunk.text}
      </p>
    </li>
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

function platformFilterLabel(platform: PlatformFilter): string {
  if (platform === "youtube") {
    return "YouTube";
  }

  if (platform === "instagram") {
    return "Instagram";
  }

  if (platform === "facebook") {
    return "Facebook";
  }

  return "All platforms";
}

function slotFilterLabel(slot: SlotFilter): string {
  if (slot === "content_1") {
    return "Content 1";
  }

  if (slot === "content_2") {
    return "Content 2";
  }

  return "Both contents";
}

function sourceTypeLabel(sourceType: string | null): string {
  if (sourceType === "metadata") {
    return "Metadata";
  }

  if (sourceType === "description") {
    return "Description/Caption";
  }

  if (sourceType === "hook") {
    return "Hook";
  }

  if (sourceType === "transcript") {
    return "Transcript";
  }

  return "All sources";
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not search indexed chunks.";
}
