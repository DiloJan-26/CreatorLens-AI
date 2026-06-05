export type ContentPlatform = "youtube" | "instagram" | "facebook";
export type ContentSlot = "content_1" | "content_2";

export type ProjectCreateRequest = {
  content_1_url: string;
  content_2_url: string;
};

export type ProjectCreateResponse = {
  project_id: string;
  status: string;
  message: string;
};

export type ExtractionStatus =
  | "pending"
  | "extracting"
  | "ready"
  | "partial"
  | "failed";

export type ContentItem = {
  id?: string | null;
  content_id?: string | null;
  slot: ContentSlot;
  platform: ContentPlatform;
  url: string;
  title?: string | null;
  creator?: string | null;
  creator_handle?: string | null;
  description?: string | null;
  caption?: string | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  reactions?: number | null;
  shares?: number | null;
  follower_count?: number | null;
  subscriber_count?: number | null;
  hashtags?: string[];
  upload_date?: string | null;
  duration_seconds?: number | null;
  engagement_rate?: number | null;
  thumbnail_url?: string | null;
  media_url?: string | null;
  audio_url?: string | null;
  metric_source_note?: string | null;
  transcript_source_note?: string | null;
  missing_fields?: string[];
  available_fields?: string[];
  completeness_score?: number | null;
  transcript_available: boolean;
  transcript_segment_count: number;
  transcript_language?: string | null;
  detected_language?: string | null;
  language_confidence?: number | null;
  transcript_source?: string | null;
  extraction_status: ExtractionStatus;
  error_message?: string | null;
};

export type VideoMetadata = ContentItem;

export type TranscriptSegment = {
  segment_index: number;
  start_time?: number | null;
  end_time?: number | null;
  text: string;
};

export type TranscriptPreviewResponse = {
  project_id: string;
  slot?: ContentSlot | null;
  platform: ContentPlatform;
  transcript_available: boolean;
  transcript_segment_count: number;
  transcript_language?: string | null;
  detected_language?: string | null;
  language_confidence?: number | null;
  transcript_source?: string | null;
  transcript_source_note?: string | null;
  segments: TranscriptSegment[];
};

export type ContentChunkCount = {
  slot?: string | null;
  label: string;
  platform: ContentPlatform | string;
  chunks: number;
};

export type IndexProjectResponse = {
  project_id: string;
  status: "indexed" | "failed";
  embedding_model: string;
  qdrant_collection: string;
  total_chunks: number;
  youtube_chunks: number;
  instagram_chunks: number;
  facebook_chunks?: number;
  chunks_by_platform?: Record<string, number>;
  chunks_by_slot?: Record<string, number>;
  chunks_by_source_type?: Record<string, number>;
  content_chunk_counts?: ContentChunkCount[];
  message?: string | null;
};

export type RetrieveProjectChunksRequest = {
  query: string;
  top_k?: number;
  platform?: ContentPlatform | null;
  slot?: ContentSlot | null;
  source_type?: "metadata" | "description" | "hook" | "transcript" | null;
};

export type RetrievedChunk = {
  content_id?: string | null;
  slot?: string | null;
  platform: string;
  source_type: string;
  score: number;
  chunk_index?: number | null;
  start_time?: number | null;
  end_time?: number | null;
  title?: string | null;
  creator?: string | null;
  citation_label: string;
  text: string;
};

export type RetrieveResponse = {
  project_id: string;
  query: string;
  applied_platform?: ContentPlatform | null;
  applied_slot?: ContentSlot | null;
  applied_source_type?: "metadata" | "description" | "hook" | "transcript" | null;
  total_results: number;
  results: RetrievedChunk[];
};

export type ChatCitation = {
  platform: string;
  source_type: string;
  citation_label: string;
  text: string;
  score?: number | null;
};

export type ChatTrace = {
  mode: "direct_metric_answer" | "gemini_rag_answer" | string;
  model: string;
  intent?: string | null;
  retrieved_sources?: number | null;
  has_creator_insights?: boolean | null;
  has_structured_metadata?: boolean | null;
  has_memory?: boolean | null;
  prompt_context_summary?: {
    structured_context_chars?: number;
    retrieved_context_chars?: number;
    insight_context_chars?: number;
    history_message_count?: number;
    citation_count?: number;
  } | null;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
  trace?: ChatTrace | null;
};

export type StoredChatMessage = {
  message_id: string;
  session_id: string;
  project_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

export type ChatHistoryResponse = {
  project_id: string;
  session_id: string;
  messages: StoredChatMessage[];
};

export type ChatStreamRequest = {
  message: string;
  session_id?: string | null;
};

export type MetricSourceMethod =
  | "public_extractor"
  | "user_verified"
  | "manual_entry"
  | "screenshot_verified"
  | "meta_api"
  | "unavailable";

export type MetricSourcePlatform =
  | "youtube"
  | "instagram"
  | "facebook"
  | "meta";

export type MetricScope =
  | "native"
  | "cross_post"
  | "combined"
  | "verified_override";

export type MetricSourceRecord = {
  id: string;
  project_id: string;
  platform: string;
  source_platform: string;
  source_method: string;
  metric_scope: string;
  url?: string | null;
  views?: number | null;
  likes?: number | null;
  reactions?: number | null;
  comments?: number | null;
  shares?: number | null;
  followers?: number | null;
  engagement_rate?: number | null;
  confidence: string;
  note?: string | null;
  created_at: string;
  updated_at: string;
};

export type MetricCompletenessItem = {
  label: string;
  status: string;
  available_fields: string[];
  missing_fields: string[];
  note?: string | null;
};

export type MetricSummaryResponse = {
  project_id: string;
  metric_completeness_score: number;
  instagram_native_status: string;
  facebook_crosspost_status: string;
  combined_meta_status: string;
  youtube_status: string;
  combined_meta_engagement_rate?: number | null;
  combined_meta_interactions?: number | null;
  combined_meta_views?: number | null;
  records: MetricSourceRecord[];
  completeness: MetricCompletenessItem[];
  notes: string[];
};

export type VerifiedMetricInput = {
  platform: MetricSourcePlatform;
  source_platform: MetricSourcePlatform;
  metric_scope: MetricScope;
  source_method?: MetricSourceMethod;
  url?: string | null;
  views?: number | null;
  likes?: number | null;
  reactions?: number | null;
  comments?: number | null;
  shares?: number | null;
  followers?: number | null;
  note?: string | null;
};

export type SaveVerifiedMetricsResponse = {
  status: string;
  record: MetricSourceRecord;
  summary: MetricSummaryResponse;
};

export type MetadataAvailabilityItem = {
  slot: ContentSlot;
  platform: ContentPlatform;
  url: string;
  available_fields: string[];
  missing_fields: string[];
  completeness_score: number;
  note: string;
};

export type MetadataAvailabilityResponse = {
  project_id: string;
  items: MetadataAvailabilityItem[];
};

export type HookAnalysis = {
  hook_text?: string | null;
  hook_type: string;
  hook_score: number;
  clarity_reason: string;
  detected_patterns: string[];
};

export type InsightScores = {
  hook_clarity: number;
  problem_solution_clarity: number;
  cta_strength: number;
  caption_strength: number;
  audience_specificity: number;
  creative_structure_score: number;
  public_performance_score: number;
  creator_efficiency_score: number;
  metadata_completeness: number;
  engagement_confidence: number;
  overall_score: number;
};

export type ContentInsight = {
  slot: string;
  label: string;
  platform: string;
  title?: string | null;
  creator?: string | null;
  hook_analysis: HookAnalysis;
  scores: InsightScores;
  strengths: string[];
  weaknesses: string[];
  missing_metadata: string[];
  available_metadata: string[];
  metric_confidence_note: string;
  top_improvement?: string | null;
};

export type ComparisonInsight = {
  confirmed_metric_winner?: string | null;
  creator_efficiency_winner?: string | null;
  creative_structure_winner?: string | null;
  hook_winner?: string | null;
  overall_insight_winner?: string | null;
  main_reason: string;
  confidence_note: string;
  top_recommendations: string[];
  example_rewrite_for_content_2?: string | null;
};

export type CreatorInsightSummaryResponse = {
  project_id: string;
  content_1?: ContentInsight | null;
  content_2?: ContentInsight | null;
  comparison: ComparisonInsight;
  notes: string[];
};

export type ProjectRecord = {
  project_id: string;
  content_1_url: string;
  content_2_url: string;
  content_1_platform: ContentPlatform;
  content_2_platform: ContentPlatform;
  youtube_url?: string | null;
  instagram_url?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ProjectDetailResponse = ProjectRecord & {
  content_items: ContentItem[];
  youtube?: ContentItem | null;
  instagram?: ContentItem | null;
};

export type HealthResponse = {
  status: string;
  service?: string;
  environment?: string;
  message?: string;
};

export type LlmHealthResponse = {
  status: string;
  provider: string;
  model: string;
  configured: boolean;
  message?: string | null;
};

export type LlmGenerationTestResponse = {
  status: string;
  provider: string;
  model: string;
  generated_text?: string | null;
  message?: string | null;
};
