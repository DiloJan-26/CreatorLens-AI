"use client";
import { useState, useRef, type FormEvent } from "react";
import { PlatformIcon } from "./PlatformIcon";
import { Icon } from "./ui";
type VideoUrlFormProps = {
  content1Url: string;
  content2Url: string;
  setContent1Url: (v: string) => void;
  setContent2Url: (v: string) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
};
export function VideoUrlForm({
  content1Url,
  content2Url,
  setContent1Url,
  setContent2Url,
  onSubmit,
  isSubmitting,
}: VideoUrlFormProps) {
  const [errors, setErrors] = useState<string[]>([]);
  const formRef = useRef<HTMLFormElement>(null);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next = [content1Url, content2Url].map((v) =>
      !v.trim()
        ? "Enter a public video URL."
        : !isSupportedUrl(v)
          ? "Use a public YouTube, Instagram Reel or Facebook Reel/watch/video URL. Copy the full video link instead of a shortened share link."
          : "",
    );
    setErrors(next);
    if (next.some(Boolean)) {
      formRef.current
        ?.querySelector<HTMLInputElement>(
          `#content-url-${next.findIndex(Boolean) + 1}`,
        )
        ?.focus();
      return;
    }
    onSubmit();
  }
  return (
    <form
      ref={formRef}
      className="compare-form"
      onSubmit={submit}
      noValidate
      aria-busy={isSubmitting}
    >
      <div className="url-pair">
        {[content1Url, content2Url].map((value, i) => (
          <div className="url-field" key={i}>
            <label htmlFor={`content-url-${i + 1}`} className="slot-label">
              <span className="slot-number">0{i + 1}</span> Content {i + 1}
            </label>
            <p className="muted text-sm mb-4">
              {i === 0
                ? "The video you want to understand."
                : "A reference to learn from."}
            </p>
            <input
              id={`content-url-${i + 1}`}
              type="url"
              inputMode="url"
              autoComplete="off"
              required
              value={value}
              disabled={isSubmitting}
              placeholder="Paste a public video URL"
              aria-invalid={Boolean(errors[i])}
              aria-describedby={`url-help${errors[i] ? ` url-error-${i}` : ""}`}
              onChange={(e) => {
                (i === 0 ? setContent1Url : setContent2Url)(e.target.value);
                setErrors([]);
              }}
            />
            {errors[i] && (
              <p id={`url-error-${i}`} className="field-error" role="alert">
                {errors[i]}
              </p>
            )}
          </div>
        ))}
      </div>
      <div className="form-actions">
        <div id="url-help">
          <p className="supported-platform-row">
            {["youtube", "instagram", "facebook"].map((platform) => (
              <span key={platform}>
                <PlatformIcon platform={platform} size={18} />
                {platform === "youtube"
                  ? "YouTube"
                  : platform === "instagram"
                    ? "Instagram"
                    : "Facebook"}
              </span>
            ))}
          </p>
          <p className="muted text-xs mt-1">
            Compare public videos from the same or different platforms.
          </p>
        </div>
        <button
          className="button-primary"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting ? "Starting analysis..." : "Analyze videos"}{" "}
          <Icon name="arrow" size={17} />
        </button>
      </div>
    </form>
  );
}
export function isSupportedUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    if (url.protocol !== "https:" || url.username || url.password || url.port) return false;
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    const path = url.pathname.toLowerCase();

    if (host === "youtu.be") {
      return /^\/[A-Za-z0-9_-]+\/?$/.test(url.pathname);
    }

    if (["youtube.com", "m.youtube.com"].includes(host)) {
      return /^\/shorts\/[A-Za-z0-9_-]+\/?$/.test(url.pathname) || path.replace(/\/$/, "") === "/watch" && /^[A-Za-z0-9_-]+$/.test(url.searchParams.get("v") ?? "");
    }

    if (["instagram.com", "m.instagram.com"].includes(host)) {
      return /^\/(reel|p|tv)\/[A-Za-z0-9_-]+\/?$/.test(url.pathname);
    }

    if (["facebook.com", "m.facebook.com"].includes(host)) {
      return path.replace(/\/$/, "") === "/watch" && /^\d+$/.test(url.searchParams.get("v") ?? "") ||
        /^\/reel\/\d+\/?$/.test(path) || /^\/[^/]+\/videos\/(?:[^/]+\/)?\d+\/?$/.test(path);
    }
  } catch {
    return false;
  }

  return false;
}
