const HERO_BADGES = [
  "YouTube",
  "Instagram",
  "Facebook",
  "Multilingual",
  "Cited AI",
];

type LandingHeroProps = {
  onStart: () => void;
};

export function LandingHero({ onStart }: LandingHeroProps) {
  return (
    <section className="relative overflow-hidden border-b border-slate-200 bg-[linear-gradient(135deg,#f8fafc_0%,#ecfeff_48%,#f0fdf4_100%)]">
      <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-teal-500 via-emerald-400 to-sky-400" />
      <div className="mx-auto grid min-h-[calc(100vh-76px)] max-w-7xl items-center gap-10 px-6 py-14 sm:px-8 lg:grid-cols-[1.05fr_0.95fr] lg:px-10">
        <div className="max-w-3xl">
          <div className="flex flex-wrap gap-2">
            {HERO_BADGES.map((badge) => (
              <span
                key={badge}
                className="rounded-full border border-teal-200 bg-white/80 px-3 py-1 text-xs font-semibold text-teal-800 shadow-sm"
              >
                {badge}
              </span>
            ))}
          </div>

          <h1 className="mt-7 max-w-4xl text-4xl font-semibold leading-tight text-slate-950 sm:text-5xl lg:text-6xl">
            Compare any two Shorts/Reels with cited creator intelligence.
          </h1>
          <p className="mt-6 max-w-3xl text-base leading-8 text-slate-700 sm:text-lg">
            Paste YouTube, Instagram, or Facebook short-form URLs. CreatorLens AI
            extracts public metadata, multilingual transcripts, hooks, captions,
            and engagement signals to explain what worked and what to improve
            next.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={onStart}
              className="inline-flex h-12 items-center justify-center rounded-md bg-slate-950 px-6 text-sm font-semibold text-white shadow-md transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-300"
            >
              Analyze Two URLs
            </button>
            <p className="text-sm font-medium text-slate-600">
              No signup required for this demo.
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-white/80 bg-white/85 p-5 shadow-xl shadow-teal-900/10 backdrop-blur">
          <div className="rounded-md border border-slate-200 bg-slate-950 p-4 text-white">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-200">
              Evidence-backed comparison
            </p>
            <div className="mt-5 grid gap-3">
              <PreviewRow label="Content 1" value="YouTube Shorts" />
              <PreviewRow label="Content 2" value="Instagram Reels" />
              <PreviewRow label="Evidence" value="Transcript, hook, caption, metadata" />
              <PreviewRow label="Output" value="Insight score, rewrite, cited chat" />
            </div>
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <HeroStat label="Metrics" value="Confirmed" />
            <HeroStat label="Transcripts" value="Multilingual" />
            <HeroStat label="Answers" value="Cited" />
          </div>
        </div>
      </div>
    </section>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-white/10 bg-white/5 px-3 py-3">
      <span className="text-sm text-slate-300">{label}</span>
      <span className="text-right text-sm font-semibold text-white">{value}</span>
    </div>
  );
}

function HeroStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-3">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-950">{value}</p>
    </div>
  );
}
