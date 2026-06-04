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
    <main className="min-h-screen bg-slate-50 px-6 py-12 text-slate-950 dark:bg-slate-950 dark:text-slate-50 sm:px-8 lg:px-10">
      <section className="mx-auto max-w-7xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
          Loading analysis workspace...
        </p>
      </section>
    </main>
  );
}
