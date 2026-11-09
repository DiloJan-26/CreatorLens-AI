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
    <div className="grid gap-5">
      <div>
        <h2 className="text-xl">Explore supporting evidence</h2>
        <p className="muted mt-2">
          Search the available source passages. Results preserve content slot,
          platform, source type and timestamps.
        </p>
      </div>
      <RetrievalTestPanel projectId={projectId} indexReady={indexReady} />
      <details open={defaultOpen} className="ui-panel">
        <summary>Advanced / Evidence index controls</summary>
        <p className="muted text-sm mb-4">
          Index status: {indexReady ? "Ready" : "Not ready"}. Indexing changes
          the available evidence and is an explicit action.
        </p>
        <RagIndexPanel
          projectId={projectId}
          initialResult={indexResult}
          onIndexed={onIndexed}
        />
      </details>
    </div>
  );
}
