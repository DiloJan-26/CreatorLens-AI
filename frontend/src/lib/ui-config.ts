/** Public build-time settings; server admission remains authoritative. */
function bounded(value: string | undefined, fallback: number, min: number, max: number): number {
  if (value === undefined || value === "") return fallback;
  const number = Number(value);
  if (!Number.isInteger(number) || number < min || number > max) throw new Error("Invalid public polling configuration.");
  return number;
}
export const uiConfig = {
  pollIntervalMs: bounded(process.env.NEXT_PUBLIC_STATUS_POLL_INTERVAL_MS, 2000, 1000, 60000),
  pollFailureLimit: bounded(process.env.NEXT_PUBLIC_STATUS_POLL_FAILURE_LIMIT, 3, 1, 10),
  semanticPollLimit: bounded(process.env.NEXT_PUBLIC_SEMANTIC_POLL_LIMIT, 60, 1, 300),
};
