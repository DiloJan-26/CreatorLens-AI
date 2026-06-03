"use client";

import { useCallback, useEffect, useState } from "react";

import { getMetadataAvailability } from "@/lib/api";
import type {
  ContentPlatform,
  MetadataAvailabilityItem,
  MetadataAvailabilityResponse,
} from "@/types/project";

type MetadataAvailabilityPanelProps = {
  projectId: string | null;
};

export function MetadataAvailabilityPanel({
  projectId,
}: MetadataAvailabilityPanelProps) {
  const [summary, setSummary] = useState<MetadataAvailabilityResponse | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeSummary =
    projectId && summary?.project_id === projectId ? summary : null;

  const loadSummary = useCallback(async (activeProjectId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      setSummary(await getMetadataAvailability(activeProjectId));
    } catch (caughtError) {
      setSummary(null);
      setError(getErrorMessage(caughtError));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!projectId) {
      return;
    }

    const loadTimer = window.setTimeout(() => {
      void loadSummary(projectId);
    }, 0);

    return () => window.clearTimeout(loadTimer);
  }, [loadSummary, projectId]);

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
            Confirmed Public Metrics
          </p>
          <h2 className="mt-2 text-xl font-semibold text-slate-950">
            Metadata Availability
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            CreatorLens AI pulls public metadata when available and marks
            missing fields as unavailable instead of estimating them.
          </p>
        </div>
        <span className="w-fit rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
          Unavailable fields are not estimated
        </span>
      </div>

      {error ? (
        <p className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {error}
        </p>
      ) : null}

      {activeSummary ? (
        <div className="mt-5 grid gap-3 lg:grid-cols-2">
          {activeSummary.items.map((item) => (
            <AvailabilityCard key={item.slot} item={item} />
          ))}
        </div>
      ) : !isLoading ? (
        <p className="mt-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          Metadata availability appears after extraction.
        </p>
      ) : (
        <p className="mt-4 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Loading metadata availability...
        </p>
      )}
    </section>
  );
}

function AvailabilityCard({ item }: { item: MetadataAvailabilityItem }) {
  return (
    <article className="rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-950">
            {slotLabel(item.slot)} - {platformLabel(item.platform)}
          </h3>
          <p className="mt-1 break-all text-xs text-slate-500">{item.url}</p>
        </div>
        <span className="w-fit rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700">
          {item.completeness_score.toFixed(0)}%
        </span>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
        <div
          className="h-full rounded-full bg-teal-500"
          style={{
            width: `${Math.max(0, Math.min(100, item.completeness_score))}%`,
          }}
        />
      </div>

      <FieldList
        title="Available fields"
        fields={item.available_fields}
        tone="available"
      />
      <FieldList
        title="Missing fields"
        fields={item.missing_fields}
        tone="missing"
      />

      <p className="mt-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-600">
        {item.note}
      </p>
    </article>
  );
}

function FieldList({
  title,
  fields,
  tone,
}: {
  title: string;
  fields: string[];
  tone: "available" | "missing";
}) {
  return (
    <div className="mt-3">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </p>
      {fields.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {fields.map((field) => (
            <span
              key={field}
              className={`rounded-full border px-2.5 py-1 text-xs font-medium ${fieldClass(tone)}`}
            >
              {fieldLabel(field)}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-600">Unavailable</p>
      )}
    </div>
  );
}

function fieldClass(tone: "available" | "missing"): string {
  if (tone === "available") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }

  return "border-amber-200 bg-amber-50 text-amber-900";
}

function slotLabel(slot: string): string {
  return slot === "content_2" ? "Content 2" : "Content 1";
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

function fieldLabel(field: string): string {
  return field.replace(/_/g, " ");
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "Could not load metadata availability.";
}
