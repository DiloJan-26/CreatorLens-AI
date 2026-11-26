import { SectionHeader } from "./SectionHeader";

const PLATFORMS = [
  {
    name: "YouTube Shorts",
    detail: "Shorts and watch URLs; public metadata and native captions.",
  },
  {
    name: "Instagram Reels",
    detail: "Public Reels and posts with source-linked video evidence.",
  },
  {
    name: "Facebook Reels",
    detail: "Public Reels, watch URLs and video posts.",
  },
];

export function SupportedPlatforms() {
  return (
    <section className="border-b border-slate-200 bg-slate-50 py-16">
      <div className="mx-auto max-w-7xl px-6 sm:px-8 lg:px-10">
        <SectionHeader
          eyebrow="Platform coverage"
          title="Built for the short-form channels creators actually compare."
          text="Evidence availability depends on public access and enabled extraction providers."
        />

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {PLATFORMS.map((platform) => (
            <article
              key={platform.name}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h3 className="text-base font-semibold text-slate-950">
                {platform.name}
              </h3>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                {platform.detail}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
