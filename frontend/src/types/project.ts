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
  segments: TranscriptSegment[];
};

export type IndexProjectResponse = {
  project_id: string;
  status: "indexed" | "failed";
  embedding_model: string;
  qdrant_collection: string;
  total_chunks: number;
  youtube_chunks: number;
  instagram_chunks: number;
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

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: ChatCitation[];
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
