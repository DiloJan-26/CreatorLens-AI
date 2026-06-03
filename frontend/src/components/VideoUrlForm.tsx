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
          placeholder="https://www.youtube.com/shorts/..."
          value={content1Url}
          onChange={setContent1Url}
        />
        <UrlCard
          label="Content 2"
          title="Content URL 2"
          placeholder="https://www.instagram.com/reel/..."
          value={content2Url}
          onChange={setContent2Url}
        />
      </div>

      {validationMessage ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {validationMessage}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={isSubmitting || !content1Url.trim() || !content2Url.trim()}
        className="inline-flex h-11 items-center justify-center rounded-md bg-teal-700 px-5 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {isSubmitting ? "Creating project..." : "Analyze Content"}
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
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-teal-700">
        {label}
      </p>
      <label className="mt-3 block text-sm font-medium text-slate-900">
        {title}
        <span className="mt-1 block text-sm font-normal leading-6 text-slate-600">
          Paste any supported short-form URL: YouTube Short, Instagram Reel, or
          Facebook Reel/post video.
        </span>
        <input
          type="url"
          placeholder={placeholder}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="mt-3 h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-teal-600 focus:ring-2 focus:ring-teal-100"
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
