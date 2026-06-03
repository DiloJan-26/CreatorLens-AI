const FEATURES = [
  {
    title: "Compare any two platforms",
    text: "YouTube vs Instagram, Instagram vs Facebook, YouTube vs YouTube, and more.",
  },
  {
    title: "Understand the first seconds",
    text: "Classify hook style, clarity, and payoff using transcript and caption evidence.",
  },
  {
    title: "Trust the metrics",
    text: "CreatorLens AI separates confirmed public metrics from unavailable fields instead of estimating.",
  },
  {
    title: "Ask follow-up questions",
    text: "Use streaming chat with citations and memory to explore why one post worked better.",
  },
  {
    title: "Go beyond transcripts",
    text: "Analyze captions, descriptions, hashtags, upload date, duration, engagement, and missing metadata.",
  },
  {
    title: "Built for real workflows",
    text: "Designed for creators, marketers, agencies, and growth teams reviewing short-form content.",
  },
];

export function FeatureGrid() {
  return (
    <section id="insights" className="border-b border-slate-200 bg-white py-16">
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
              className="rounded-lg border border-slate-200 bg-slate-50 p-5 shadow-sm"
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
