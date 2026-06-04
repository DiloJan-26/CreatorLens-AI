import { SectionHeader } from "./SectionHeader";

const PLATFORMS = [
  {
    name: "YouTube Shorts",
    detail: "Public Shorts and watch URLs with captions when available.",
  },
  {
    name: "Instagram Reels",
    detail: "Best-effort public metadata, captions, hashtags, and audio transcription.",
  },
  {
    name: "Facebook Reels",
    detail: "Best-effort public Reels, watch URLs, and post video extraction.",
  },
];

export function SupportedPlatforms() {
  return (
    <section className="border-b border-slate-200 bg-slate-50 py-16 dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-10">
        <SectionHeader
          eyebrow="Supported platforms"
          title="Built for the short-form channels creators actually compare."
          text="CreatorLens AI keeps cross-platform comparisons clear with Content 1 and Content 2 labels, platform names, and confirmed public metric boundaries."
        />

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {PLATFORMS.map((platform) => (
            <article
              key={platform.name}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <h3 className="text-base font-semibold text-slate-950 dark:text-slate-50">
                {platform.name}
              </h3>
              <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {platform.detail}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
