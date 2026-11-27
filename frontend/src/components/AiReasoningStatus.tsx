"use client";

import { useEffect, useRef, useState } from "react";
import { checkEngineeringLlm } from "@/lib/api";
import { ApiError } from "@/lib/auth-transport";
import { useEngineering } from "./EngineeringAccess";

type CheckState = "untested" | "checking" | "reachable" | "failed";

export function LlmAvailabilityCheck({projectId}: {projectId: string | null}) {
  const {refresh} = useEngineering();
  const [state, setState] = useState<CheckState>("untested");
  const [message, setMessage] = useState("Not checked. A manual check may incur provider charges.");
  const [cooldown, setCooldown] = useState(false);
  const pending = useRef(false);
  const mounted = useRef(true);
  const cooldownTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => {mounted.current = false; if (cooldownTimer.current) clearTimeout(cooldownTimer.current);};
  }, []);

  async function check() {
    if (!projectId || pending.current || cooldown) return;
    pending.current = true;
    setState("checking");
    setMessage("Checking the configured LLM...");
    try {
      const result = await checkEngineeringLlm(projectId);
      if (!mounted.current) return;
      if (!["reachable", "blocked", "failed"].includes(result.status) || !Number.isFinite(Date.parse(result.checked_at))) {
        throw new Error("Invalid diagnostic response.");
      }
      setState(result.status === "reachable" && result.provider_invocation_count === 1 ? "reachable" : "failed");
      setMessage(`${result.message} (${result.model}; ${new Date(result.checked_at).toLocaleTimeString()})`);
      const seconds = result.retry_after_seconds || (result.provider_invocation_count ? 60 : 0);
      if (seconds > 0) {
        setCooldown(true);
        cooldownTimer.current = setTimeout(() => {if (mounted.current) setCooldown(false);}, seconds * 1000);
      }
    } catch (error) {
      if (!mounted.current) return;
      setState("failed");
      setMessage(error instanceof ApiError ? error.message : "The check could not be completed. Gemini availability is unknown.");
      if (error instanceof ApiError && error.status === 403) void refresh();
    } finally {
      pending.current = false;
    }
  }

  const status = projectId ? message : "Open a completed analysis to check the LLM.";
  return (
    <span className="llm-check-control">
      <button type="button" className="llm-check-button" onClick={() => void check()}
        disabled={!projectId || state === "checking" || cooldown}
        aria-label="Check LLM availability" aria-busy={state === "checking"}
        title={`${status}${cooldown ? " Check cooldown active." : ""}`}>
        {state === "checking" ? "Checking..." : "Check LLM"}
        <span className={`llm-check-dot llm-check-${state}`} aria-hidden="true"/>
      </button>
      <span className="sr-only" role="status" aria-live="polite">{status}</span>
    </span>
  );
}
