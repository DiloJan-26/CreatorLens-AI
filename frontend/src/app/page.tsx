import Link from "next/link";
import { Icon } from "@/components/ui";
import { LandingComparisonPreview } from "@/components/LandingComparisonPreview";

export default function Home() {
  return (
    <main className="landing">
      <section className="landing-hero" id="product">
        <div className="hero-main">
          <div className="hero-copy">
            <p className="hero-kicker">
              <Icon name="shield" size={16} /> AI for creator intelligence
            </p>
            <h1>
              Understand what makes
              <br className="hero-line-break" /> one video stand out.
            </h1>
            <p className="hero-description">
              Compare two public videos using confirmed metrics, transcript
              evidence and a cited AI assistant powered by RAG.
            </p>
            <div className="hero-actions">
              <Link className="button-primary" href="/analyze">
                Try CreatorLens <Icon name="arrow" size={18} />
              </Link>
              <a className="button-secondary" href="#how-it-works">
                See how it works
              </a>
            </div>
            <p className="hero-footnote">
              YouTube / Instagram / Facebook <span aria-hidden="true"> / </span>{" "}
              No sign-in required
            </p>
          </div>
          <LandingComparisonPreview />
        </div>
        <ul
          className="hero-capabilities"
          id="features"
          aria-label="Product capabilities"
        >
          {[
            ["evidence", "Evidence-backed", "Follow every source"],
            ["globe", "Cross-platform", "Keep context in view"],
            ["chat", "RAG assistant", "Ask grounded questions"],
            ["chart", "Evaluation & LLMOps", "Inspect the engineering"],
          ].map(([icon, title, detail]) => (
            <li key={title}>
              <span className="capability-icon">
                <Icon name={icon} size={23} />
              </span>
              <div>
                <strong>{title}</strong>
                <span>{detail}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <section className="workflow-section" id="how-it-works">
        <div>
          <p className="eyebrow">A focused workflow</p>
          <h2>
            Two perspectives.
            <br />
            One informed next move.
          </h2>
        </div>
        <ol className="workflow-list">
          {[
            [
              "Compare",
              "Paste two public video URLs. Compare across supported platforms while keeping their differences visible.",
            ],
            [
              "Investigate",
              "Review available metrics, deterministic insight scores, and the transcript behind the opening hook.",
            ],
            [
              "Ask & act",
              "Ask the assistant for explanations and improvements. Follow its citations and review the limitations.",
            ],
          ].map(([title, text], i) => (
            <li key={title}>
              <span className="step-number">0{i + 1}</span>
              <div>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
      <section className="evidence-story">
        <div>
          <p className="eyebrow">Designed for scrutiny</p>
          <h2>
            An answer is only useful
            <br />
            if you can inspect its basis.
          </h2>
          <p className="muted mt-5 max-w-lg">
            CreatorLens separates what was observed, what was calculated, and
            what AI suggests. It helps you form creative hypotheses without
            presenting them as proven causes of performance.
          </p>
          <Link href="/analyze" className="button-quiet mt-5">
            Open the comparison workspace <Icon name="arrow" />
          </Link>
        </div>
        <div className="evidence-ledger">
          {[
            [
              "01",
              "Observed",
              "Confirmed public metrics and extracted transcript passages, with source availability.",
            ],
            [
              "02",
              "Calculated",
              "Deterministic Creator Insight Scores. Heuristic assessments, not platform analytics.",
            ],
            [
              "03",
              "Interpreted",
              "Evidence-grounded AI explanations and recommendations, with citations and limitations.",
            ],
          ].map(([n, t, d]) => (
            <div key={n}>
              <span className="muted font-mono text-xs">{n}</span>
              <div>
                <h3>{t}</h3>
                <p>{d}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section className="engineering-story">
        <div>
          <p className="eyebrow">Open engineering console</p>
          <h2>See the system behind the answer.</h2>
          <p className="muted mt-3">
            Inspect deterministic regression results, retrieval quality signals,
            token usage and latency. Read-only visibility into the RAG pipeline.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link className="button-secondary" href="/evaluations">
            RAG Evaluation <Icon name="arrow" />
          </Link>
          <Link className="button-secondary" href="/dashboard">
            LLM Observability <Icon name="arrow" />
          </Link>
        </div>
      </section>
      <section className="landing-limitations">
        <h2>Useful evidence. Honest boundaries.</h2>
        <p>
          Public extraction is best-effort. Missing metrics remain unavailable.
          Different platforms, audiences and publishing dates limit direct
          comparisons. AI recommendations are suggestions to test—not guarantees
          of reach or engagement.
        </p>
      </section>
      <section className="landing-final">
        <div>
          <p className="eyebrow">Start with a real question</p>
          <h2>What could your next video do differently?</h2>
        </div>
        <Link className="button-primary" href="/analyze">
          Compare two videos <Icon name="arrow" />
        </Link>
      </section>
      <footer className="landing-footer">
        <strong>CreatorLens AI</strong>
        <p>Public evidence. Clearer creative decisions.</p>
        <Link href="/evaluations">Explore the engineering</Link>
      </footer>
    </main>
  );
}
