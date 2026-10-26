export type NumericValue = number | string;

export type CostTotals = {
  event_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: NumericValue | null;
};

export type LlmRunSummary = {
  id: string;
  project_id: string;
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
};

export type CostMetricsResponse = {
  project_id: string | null;
  totals: CostTotals;
  runs: LlmRunSummary[];
};
