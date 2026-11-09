import Link from "next/link";
import { Icon } from "./ui";

export function LandingComparisonPreview() {
  return (
    <figure
      className="comparison-preview"
      aria-label="Illustration of two videos and the evidence available for comparison"
    >
      <div className="preview-toolbar">
        <span className="preview-dot" /> Two videos. A clearer perspective.
        <span className="preview-example">Illustrative preview</span>
      </div>
      <div className="preview-composition">
        <div className="preview-pair">
          <div className="preview-video">
            <div className="preview-poster poster-outdoors">
              <VideoIllustration scene="outdoors" />
              <span className="poster-label">VIDEO 01</span>
              <span className="poster-play" aria-hidden="true">
                <PlayGlyph />
              </span>
              <div className="poster-copy">
                <span>A new perspective</span>
                <strong>
                  Start with
                  <br />a story.
                </strong>
              </div>
            </div>
            <p>The opening story</p>
          </div>
          <div className="preview-video">
            <div className="preview-poster poster-studio">
              <VideoIllustration scene="studio" />
              <span className="poster-label">VIDEO 02</span>
              <span className="poster-play" aria-hidden="true">
                <PlayGlyph />
              </span>
              <div className="poster-copy">
                <span>A different angle</span>
                <strong>
                  Make every
                  <br />
                  frame count.
                </strong>
              </div>
            </div>
            <p>A different approach</p>
          </div>
        </div>
        <div className="preview-result">
          <p className="preview-result-label">Comparison workspace</p>
          <span className="preview-result-symbol">
            <Icon name="compare" size={23} />
          </span>
          <h2>
            Go beyond
            <br />
            the view count.
          </h2>
          <ul>
            <li>
              <Icon name="check" size={16} />
              <span>Confirmed public metrics</span>
            </li>
            <li>
              <Icon name="check" size={16} />
              <span>Opening hooks &amp; structure</span>
            </li>
            <li>
              <Icon name="check" size={16} />
              <span>Cited transcript evidence</span>
            </li>
          </ul>
          <Link href="/analyze">
            Explore comparison <Icon name="arrow" size={16} />
          </Link>
        </div>
      </div>
      <figcaption className="preview-caption">
        Illustrations, not analyzed videos. Your results use your URLs and
        available evidence.
      </figcaption>
    </figure>
  );
}

function PlayGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="21" height="21" fill="currentColor">
      <path d="m9 5 11 7-11 7Z" />
    </svg>
  );
}

function VideoIllustration({ scene }: { scene: "outdoors" | "studio" }) {
  if (scene === "outdoors")
    return (
      <svg
        viewBox="0 0 200 330"
        preserveAspectRatio="xMidYMid slice"
        className="poster-art"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="outdoor-sky" x2="0" y2="1">
            <stop stopColor="#cbded5" />
            <stop offset="1" stopColor="#eef0d8" />
          </linearGradient>
        </defs>
        <path fill="url(#outdoor-sky)" d="M0 0h200v330H0z" />
        <circle cx="151" cy="74" r="32" fill="#faf5d3" />
        <path d="m-35 199 93-107 70 84 55-60 57 94v120H0Z" fill="#91aca0" />
        <path d="m-18 231 86-78 78 69 75-66v174H0Z" fill="#526f61" />
        <path d="M-20 287c70-106 127-80 245-37v80H0Z" fill="#294c40" />
        <path
          d="M105 330c-45-62-54-88-29-125 9-13 18-19 28-24-17 22-28 35-22 55 6 24 49 52 62 94"
          fill="#d9c7a1"
          opacity=".9"
        />
        <path
          d="m25 141 8-25 9 25h-5l9 20H22l8-20Zm116 57 9-30 10 30h-5l10 23h-28l10-23Z"
          fill="#36594a"
        />
      </svg>
    );
  return (
    <svg
      viewBox="0 0 200 330"
      preserveAspectRatio="xMidYMid slice"
      className="poster-art"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="studio-wall" x2="1" y2="1">
          <stop stopColor="#e4bda2" />
          <stop offset="1" stopColor="#a97d67" />
        </linearGradient>
      </defs>
      <path fill="url(#studio-wall)" d="M0 0h200v330H0z" />
      <path d="M100 0h9v224h-9zM0 107h200v7H0z" fill="#6c6757" opacity=".25" />
      <path d="M17 25h70v128H17z" fill="#e8dfc3" opacity=".8" />
      <path d="m17 122 70-57v88H17Z" fill="#9cb1a0" />
      <ellipse cx="111" cy="226" rx="80" ry="22" fill="#744e3d" opacity=".25" />
      <path d="M70 193c0-35 11-58 39-58s46 31 46 58v76H70Z" fill="#305f54" />
      <ellipse cx="111" cy="113" rx="24" ry="31" fill="#dab594" />
      <path
        d="M86 115V96c0-31 51-35 51 3v18l-9-16c-13 0-20-6-23-9l-12 25Z"
        fill="#353a31"
      />
      <path d="M26 220h161v16H26z" fill="#d2b28a" />
      <path d="m125 190 7-32h45l-7 32Z" fill="#e5e7dc" />
      <path d="M113 189h57v5h-57z" fill="#eef0e5" />
      <path d="M39 192h15v25H39z" fill="#faf1d6" />
      <path d="M0 265h200v65H0Z" fill="#41534b" />
    </svg>
  );
}
