type RecommendationListProps = {
  recommendations: string[];
  exampleRewrite?: string | null;
};

export function RecommendationList({
  recommendations,
  exampleRewrite,
}: RecommendationListProps) {
  return (
    <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
        Recommendations
      </p>
      <h3 className="mt-2 text-base font-semibold text-slate-950">
        Top recommendations
      </h3>

      {recommendations.length > 0 ? (
        <ol className="mt-4 grid gap-2">
          {recommendations.map((recommendation, index) => (
            <li
              key={`${recommendation}-${index}`}
              className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm leading-6 text-slate-700"
            >
              <span className="mr-2 font-semibold text-slate-950">
                {index + 1}.
              </span>
              {recommendation}
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-4 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600">
          Recommendations unavailable until enough creator evidence is extracted.
        </p>
      )}

      {exampleRewrite ? (
        <div className="mt-5 rounded-md border border-teal-200 bg-white px-3 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-teal-700">
            Example Rewrite
          </p>
          <p className="mt-2 text-sm leading-6 text-slate-700">
            {exampleRewrite}
          </p>
        </div>
      ) : null}
    </section>
  );
}
