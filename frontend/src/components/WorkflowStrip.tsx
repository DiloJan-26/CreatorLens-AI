const STEPS = [
  "Paste URLs",
  "Extract metadata and transcripts",
  "Build cited evidence",
  "Get creator insights",
  "Ask follow-up questions",
];

export function WorkflowStrip() {
  return (
    <section id="how-it-works" className="border-b border-slate-200 bg-slate-950 py-10 text-white">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-10">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-200">
              How it works
            </p>
            <h2 className="mt-2 text-2xl font-semibold">
              One analysis, five evidence-backed steps.
            </h2>
          </div>
          <p className="max-w-xl text-sm leading-6 text-slate-300">
            The workspace turns two URLs into cited insights without exposing
            backend or retrieval controls in the normal user flow.
          </p>
        </div>

        <ol className="mt-8 grid gap-3 md:grid-cols-5">
          {STEPS.map((step, index) => (
            <li
              key={step}
              className="rounded-lg border border-white/10 bg-white/5 p-4"
            >
              <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-teal-300 text-xs font-semibold text-slate-950">
                {index + 1}
              </span>
              <p className="mt-4 text-sm font-semibold leading-6">{step}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
