import Link from "next/link";

export function WorkspaceCTA() {
  return (
    <section className="bg-white px-6 py-16 sm:px-8 lg:px-10">
      <div className="mx-auto max-w-7xl overflow-hidden rounded-2xl border border-slate-200 bg-[linear-gradient(135deg,#0f172a_0%,#134e4a_55%,#0369a1_100%)] p-8 text-white shadow-xl shadow-slate-900/10 lg:p-10">
        <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-200">
              Your creator workspace
            </p>
            <h2 className="mt-3 text-3xl font-semibold">
              Ready to compare two pieces of content?
            </h2>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-200 sm:text-base">
              Explore the evidence-first workflow. Live extraction and model generation
              require verified pricing and usage admission. Sign in with Google to access
              your private workspace and existing analyses.
            </p>
          </div>
          <Link
            href="/analyze"
            className="inline-flex h-12 items-center justify-center rounded-md bg-white px-6 text-sm font-semibold text-slate-950 transition hover:bg-teal-50"
          >
            Explore workspace
          </Link>
        </div>
      </div>
    </section>
  );
}
