"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getDemoCapabilities, checkLlmHealth, testLlmGeneration } from "@/lib/api";

type ReasoningState = "untested" | "active" | "unavailable";

export function AiReasoningStatus() {
  const [state, setState] = useState<ReasoningState>("untested");
  const [checking, setChecking] = useState(false);
  const [providerAllowed, setProviderAllowed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const initialized = useRef(false);

  // On mount: config check only (no generation call).
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    getDemoCapabilities().then(value => setProviderAllowed(value.provider_calls_enabled)).catch(() => {});

    checkLlmHealth()
      .then((res) => {
        if (res.status === "ok" && res.configured) {
          setState("untested");
        } else {
          setState("unavailable");
          setMessage(res.message ?? "AI Reasoning not configured.");
        }
      })
      .catch(() => {
        setState("unavailable");
        setMessage("Backend unreachable.");
      });
  }, []);

  const handleCheck = useCallback(async () => {
    if (checking || !providerAllowed) return;
    setChecking(true);
    setMessage(null);

    try {
      const res = await testLlmGeneration();

      if (res.status === "ok") {
        setState("active");
        setMessage(null);
      } else {
        setState("unavailable");
        setMessage("AI Reasoning check failed. Verify API key and model access.");
      }
    } catch {
      setState("unavailable");
      setMessage("Could not reach AI Reasoning service.");
    } finally {
      setChecking(false);
    }
  }, [checking, providerAllowed]);

  const dot =
    state === "active"
      ? "bg-emerald-500"
      : state === "unavailable"
        ? "bg-red-500"
        : "bg-amber-400";

  const label =
    state === "active"
      ? "AI Reasoning Active"
      : state === "unavailable"
        ? "AI Reasoning Unavailable"
        : "AI Reasoning Not Tested";

  return (
    <div className="flex items-center gap-1.5">
      <span
        title={message ?? label}
        className={`h-2 w-2 shrink-0 rounded-full ${dot}`}
        aria-label={label}
      />
      <span className="hidden text-xs font-medium text-slate-500 lg:inline">
        {label}
      </span>
      <button
        type="button"
        onClick={handleCheck}
        disabled={checking || !providerAllowed}
        aria-label="Check AI Reasoning"
        className="rounded px-1.5 py-0.5 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 disabled:cursor-not-allowed"
      >
        {checking ? "…" : "Check"}
      </button>
    </div>
  );
}
