export type EvaluationAnswerType = "metric" | "comparison" | "recommendation";

export type EvaluationDatasetSummary = {
  methodology?: string;
  evaluator?: string | null;
  name: string;
  version: string;
  case_count: number;
  answer_types: EvaluationAnswerType[];
};

export type EvaluationPublication = {
  policy_version?: string;
  publication_key?: string;
  source_commit?: string | null;
  source_commit_origin?: string;
  source_state?: string;
  source_fingerprint?: string;
  dataset_fingerprint?: string;
  report_fingerprint?: string;
  fingerprint_policy?: string;
  result_fingerprint?: string;
  non_reproducible_result?: boolean;
  execution_mode?: string;
  reference_scope?: string;
  provider_invocation_count?: number;
  published_at?: string;
  python_version?: string;
  dependency_versions?: Record<string,string>;
  not_executed_cases?: number;
};

export type EvaluationRunSummary = {
  publication?: EvaluationPublication;
  source_status?: "current" | "different" | "unverified";
  skipped_cases?: number;
  evaluation_details?: IntelligenceEvaluationDetails;
  id: string;
  dataset_name: string;
  dataset_version: string;
  status: string;
  evaluator: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  aggregate_metrics: Record<string, unknown>;
  error_code: string | null;
  created_at: string;
  completed_at: string | null;
};

export type EvaluationCheckResult = {
  passed: boolean;
  score: number;
  message: string;
};

export type EvaluationResultSummary = {
  scenario?: string | null;
  answer_text?: string | null;
  evaluation_details?: {
    category?: string; execution_mode?: string; critical?: boolean; fixture_id?: string;
    actual_output?: Record<string, unknown>; expected_output?: Record<string, unknown>;
    failure_reasons?: string[]; skip_reason?: string | null; references?: string[];
  };
  case_id: string;
  status: string;
  answer_type: string | null;
  citation_labels: string[];
  metric_scores: Record<string, unknown>;
  rubric_results: Record<string, EvaluationCheckResult>;
  duration_ms: number | null;
  error_code: string | null;
};

export type EvaluationRunDetail = {
  run: EvaluationRunSummary;
  results: EvaluationResultSummary[];
};


export type IntelligenceEvaluationDetails = {
  methodology?: string;
  dataset_fingerprint?: string;
  critical_gate?: { passed: boolean; passed_cases: number; failed_cases: number; skipped_cases: number; total_cases: number; policy: string };
  categories?: Record<string, { passed: number; failed: number; skipped: number; total: number }>;
  execution_modes?: Record<string, { passed: number; failed: number; skipped: number; total: number }>;
  indicators?: Record<string, { numerator: number; denominator: number; value: number | null; mode: string }>;
  grounding_confusion?: Record<string, number>;
  limitations?: string[];
};
