const FEATURES = [
  {
    title: "Cross-platform comparison",
    text: "Compare YouTube vs Instagram, Instagram vs Facebook, YouTube vs YouTube, and more.",
  },
  {
    title: "Hook intelligence",
    text: "Analyze the first seconds, hook type, clarity, and payoff.",
  },
  {
    title: "Confirmed public metrics",
    text: "Separate extracted metrics from unavailable fields instead of estimating.",
  },
  {
    title: "Multilingual transcripts",
    text: "Use captions and multilingual transcription for global creator content.",
  },
  {
    title: "Cited AI chat",
    text: "Ask follow-up questions with streaming answers grounded in retrieved evidence.",
  },
  {
    title: "Creator insight summary",
    text: "Get heuristic scores, recommendations, and rewrite ideas for the next post.",
  },
];

export function FeatureGrid() {
  return (
    <section id="insights" className="border-b border-slate-200 bg-white py-16 dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-10">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
            Creator intelligence
          </p>
          <h2 className="mt-3 text-3xl font-semibold text-slate-950">
            Insight-first analysis for short-form reviews.
          </h2>
          <p className="mt-4 text-sm leading-7 text-slate-600 sm:text-base">
            CreatorLens AI keeps public evidence, missing metadata, and AI
            recommendations visible so teams can make better creative decisions.
          </p>
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <article
              key={feature.title}
              className="rounded-2xl border border-slate-200 bg-slate-50 p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <h3 className="text-base font-semibold text-slate-950">
                {feature.title}
              </h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                {feature.text}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
