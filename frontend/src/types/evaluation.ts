export type EvaluationAnswerType = "metric" | "comparison" | "recommendation";

export type EvaluationDatasetSummary = {
  methodology?: string;
  evaluator?: string | null;
  name: string;
  version: string;
  case_count: number;
  answer_types: EvaluationAnswerType[];
};

export type EvaluationRunSummary = {
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
