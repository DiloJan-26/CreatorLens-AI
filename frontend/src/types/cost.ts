export type NumericValue = number | string;

export type CostTotals = {
  event_count: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  estimated_cost_usd: NumericValue | null;
  priced_subtotal_usd?: NumericValue | null;
  total_operations?: number;
  model_invocations?: number;
  inference_events?: number;
  priced_inference_events?: number;
  unpriced_inference_events?: number;
  deterministic_operations?: number;
  legacy_invocation_unknown?: number;
  pricing_coverage?: number | null;
  verified_pricing_coverage?: number | null;
  legacy_estimate_events?: number;
  cost_status?: string;
};

export type LlmRunSummary = {
  id: string;
  project_id: string | null;
  session_id: string | null;
  retrieval_run_id: string | null;
  langsmith_trace_id: string | null;
  status: string;
  llm_provider: string;
  llm_model: string;
  prompt_name: string | null;
  prompt_version: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  retrieval_latency_ms: number | null;
  llm_latency_ms: number | null;
  retrieved_chunk_count: number | null;
  source_balance: Record<string, unknown>;
  cache_hit: boolean | null;
  cache_miss: boolean | null;
  transcript_provider: string | null;
  transcript_fallback_used: boolean | null;
  embedding_reused: boolean | null;
  error_code: string | null;
  created_at: string;
  completed_at: string | null;
  operation_type?: string | null;
  execution_mode?: string | null;
  provider_invocation_count?: number | null;
  end_to_end_latency_ms?: number | null;
  context_latency_ms?: number | null;
  deterministic_latency_ms?: number | null;
  telemetry?: {usage?: Record<string, unknown>; content_id?: string; snapshot_id?: string} | null;
  cost_events?: {estimated_cost_usd: NumericValue | null; estimate_details?: {
    status: string; reason?: string; model?: string; policy_version?: string; service_tier?: string;
    components?: Record<string, string>; priced_subtotal_usd?: NumericValue | null;
  } | null}[];
};

export type CostMetricsResponse = {
  project_id: string | null;
  totals: CostTotals;
  analytics?: {
    latencies?: Record<string, {samples: number; mean_ms: number | null; p50_ms: number | null; p95_ms: number | null}>;
    operations?: Record<string, number>;
    daily?: {date: string; operations: number; model_invocations: number}[];
    legacy_latency_excluded?: number;
    latency_policy?: string;
  };
  runs: LlmRunSummary[];
};
