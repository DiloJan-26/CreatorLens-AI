import { Suspense } from "react";

import { ComparisonWorkspace } from "@/components/ComparisonWorkspace";

export default function AnalyzePage() {
  return (
    <Suspense fallback={<AnalyzeLoading />}>
      <ComparisonWorkspace />
    </Suspense>
  );
}

function AnalyzeLoading() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12 text-slate-950 sm:px-8 lg:px-10">
      <section className="mx-auto max-w-7xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold text-slate-950">
          Loading analysis workspace...
        </p>
      </section>
    </main>
  );
}
