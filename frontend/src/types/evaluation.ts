export type EvaluationAnswerType = "metric" | "comparison" | "recommendation";

export type EvaluationDatasetSummary = {
  name: string;
  version: string;
  case_count: number;
  answer_types: EvaluationAnswerType[];
};

export type EvaluationRunSummary = {
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
