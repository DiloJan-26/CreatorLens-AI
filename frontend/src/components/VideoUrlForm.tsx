"use client";
import { useState, useRef, type FormEvent } from "react";
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
          ? "Use a supported YouTube, Instagram or Facebook video URL."
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
          <p className="text-sm font-medium">YouTube / Instagram / Facebook</p>
          <p className="muted text-xs mt-1">
            Public videos only. Availability varies by platform.
          </p>
        </div>
        <button
          className="button-primary"
          disabled={isSubmitting}
          type="submit"
        >
          {isSubmitting ? "Starting analysis..." : "Analyze videos"}
        </button>
      </div>
    </form>
  );
}
function isSupportedUrl(value: string): boolean {
  try {
    const url = new URL(value.trim());
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    const path = url.pathname.toLowerCase();

    if (host === "youtu.be") {
      return Boolean(path.replace("/", ""));
    }

    if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      return path.startsWith("/shorts/") || path === "/watch";
    }

    if (host === "instagram.com" || host.endsWith(".instagram.com")) {
      return (
        path.startsWith("/reel/") ||
        path.startsWith("/p/") ||
        path.startsWith("/tv/")
      );
    }

    if (host === "fb.watch") {
      return Boolean(path.replace("/", ""));
    }

    if (host === "facebook.com" || host.endsWith(".facebook.com")) {
      return (
        path.startsWith("/reel/") ||
        path.startsWith("/watch") ||
        path.includes("/videos/") ||
        path.startsWith("/share/r/")
      );
    }
  } catch {
    return false;
  }

  return false;
}
