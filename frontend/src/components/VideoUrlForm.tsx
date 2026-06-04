import type { FormEvent } from "react";
import { useState } from "react";

type VideoUrlFormProps = {
  content1Url: string;
  content2Url: string;
  setContent1Url: (value: string) => void;
  setContent2Url: (value: string) => void;
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
  const [validationMessage, setValidationMessage] = useState<string | null>(
    null,
  );
  const canAnalyze = Boolean(content1Url.trim() && content2Url.trim());

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!content1Url.trim() || !content2Url.trim()) {
      setValidationMessage("Enter Content URL 1 and Content URL 2.");
      return;
    }

    if (!isSupportedUrl(content1Url) || !isSupportedUrl(content2Url)) {
      setValidationMessage(
        "Use a YouTube Short, Instagram Reel, or Facebook Reel/post video URL.",
      );
      return;
    }

    setValidationMessage(null);
    onSubmit();
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
        <UrlCard
          label="Content 1"
          title="Content URL 1"
          placeholder="Paste a YouTube Short, Instagram Reel, or Facebook Reel URL"
          value={content1Url}
          onChange={setContent1Url}
        />
        <UrlCard
          label="Content 2"
          title="Content URL 2"
          placeholder="Paste a YouTube Short, Instagram Reel, or Facebook Reel URL"
          value={content2Url}
          onChange={setContent2Url}
        />
      </div>

      {validationMessage ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
          {validationMessage}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={isSubmitting || !canAnalyze}
        className={`inline-flex h-12 items-center justify-center gap-2 rounded-md border px-5 text-sm font-semibold transition-all ${
          isSubmitting
            ? "cursor-wait border-emerald-300/60 bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-lg shadow-emerald-500/20 ring-1 ring-emerald-300/50 dark:border-emerald-400/40 dark:shadow-emerald-400/15"
            : canAnalyze
            ? "border-emerald-300/70 bg-gradient-to-r from-emerald-500 to-teal-500 text-white shadow-lg shadow-emerald-500/25 ring-1 ring-emerald-300/60 hover:scale-[1.01] hover:shadow-emerald-500/40 dark:border-emerald-400/50 dark:shadow-emerald-400/20"
            : "cursor-not-allowed border-slate-300 bg-slate-200 text-slate-500 shadow-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-500"
        }`}
      >
        {isSubmitting ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            Analyzing...
          </>
        ) : (
          "Analyze Content"
        )}
      </button>
    </form>
  );
}

type UrlCardProps = {
  label: string;
  title: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
};

function UrlCard({
  label,
  title,
  placeholder,
  value,
  onChange,
}: UrlCardProps) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700 dark:text-teal-300">
        {label}
      </p>
      <label className="mt-3 block text-sm font-medium text-slate-900 dark:text-slate-100">
        {title}
        <span className="mt-1 block text-sm font-normal leading-6 text-slate-600 dark:text-slate-300">
          Paste any supported short-form URL from YouTube, Instagram, or
          Facebook.
        </span>
        <input
          type="url"
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="mt-3 h-12 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-400/60 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 dark:placeholder:text-slate-500 dark:focus:border-emerald-400"
        />
      </label>
    </section>
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
