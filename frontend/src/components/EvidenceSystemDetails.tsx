"use client";

import type { IndexProjectResponse } from "@/types/project";

import { RagIndexPanel } from "./RagIndexPanel";
import { RetrievalTestPanel } from "./RetrievalTestPanel";

type EvidenceSystemDetailsProps = {
  projectId: string | null;
  indexResult: IndexProjectResponse | null;
  indexReady: boolean;
  defaultOpen?: boolean;
  onIndexed: (result: IndexProjectResponse) => void;
};

export function EvidenceSystemDetails({
  projectId,
  indexResult,
  indexReady,
  defaultOpen = false,
  onIndexed,
}: EvidenceSystemDetailsProps) {
  return (
    <details
      id="evidence"
      open={defaultOpen}
      className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
    >
      <summary className="cursor-pointer list-none">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
              Evidence & System Details
            </p>
            <h2 className="mt-2 text-base font-semibold text-slate-950">
              Advanced validation layer
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              Inspect the evidence index and retrieved sources used to ground
              cited answers. This section is collapsed by default for normal
              creator workflows.
            </p>
          </div>
          <span className="w-fit rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
            Evidence index: {indexReady ? "Ready" : "Not ready"}
          </span>
        </div>
      </summary>

      <div className="mt-5 grid gap-4">
        <RagIndexPanel
          projectId={projectId}
          initialResult={indexResult}
          onIndexed={onIndexed}
        />
        <RetrievalTestPanel projectId={projectId} indexReady={indexReady} />
      </div>
    </details>
  );
}
