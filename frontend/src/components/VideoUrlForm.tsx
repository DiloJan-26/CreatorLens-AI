import type { FormEvent } from "react";
import { useState } from "react";

type VideoUrlFormProps = {
  youtubeUrl: string;
  instagramUrl: string;
  setYoutubeUrl: (value: string) => void;
  setInstagramUrl: (value: string) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
};

export function VideoUrlForm({
  youtubeUrl,
  instagramUrl,
  setYoutubeUrl,
  setInstagramUrl,
  onSubmit,
  isSubmitting,
}: VideoUrlFormProps) {
  const [validationMessage, setValidationMessage] = useState<string | null>(
    null,
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!youtubeUrl.trim() || !instagramUrl.trim()) {
      setValidationMessage("Enter both YouTube and Instagram URLs.");
      return;
    }

    setValidationMessage(null);
    onSubmit();
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
        <UrlCard
          label="YouTube"
          title="YouTube Short URL"
          placeholder="https://www.youtube.com/shorts/..."
          value={youtubeUrl}
          onChange={setYoutubeUrl}
        />
        <UrlCard
          label="Instagram"
          title="Instagram Reel URL"
          placeholder="https://www.instagram.com/reel/..."
          value={instagramUrl}
          onChange={setInstagramUrl}
        />
      </div>

      {validationMessage ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {validationMessage}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={isSubmitting}
        className="inline-flex h-11 items-center justify-center rounded-md bg-teal-700 px-5 text-sm font-medium text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-400"
      >
        {isSubmitting ? "Creating project..." : "Analyze Videos"}
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
