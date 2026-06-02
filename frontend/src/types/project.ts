export type ProjectCreateRequest = {
  youtube_url: string;
  instagram_url: string;
};

export type ProjectCreateResponse = {
  project_id: string;
  status: string;
  message: string;
};

export type VideoMetadata = {
  platform: "youtube" | "instagram";
  url: string;
  title?: string | null;
  description?: string | null;
  creator?: string | null;
  follower_count?: number | null;
  views?: number | null;
  likes?: number | null;
  comments?: number | null;
  hashtags?: string[];
  upload_date?: string | null;
  duration_seconds?: number | null;
  engagement_rate?: number | null;
  transcript_available: boolean;
  transcript_segment_count: number;
  extraction_status: "pending" | "extracting" | "ready" | "partial" | "failed";
  error_message?: string | null;
  metric_source_note?: string | null;
  transcript_source_note?: string | null;
};

export type TranscriptSegment = {
  segment_index: number;
  start_time?: number | null;
  end_time?: number | null;
  text: string;
};

export type TranscriptPreviewResponse = {
  project_id: string;
  platform: "youtube" | "instagram";
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
  platform?: "youtube" | "instagram" | null;
  source_type?: "metadata" | "description" | "hook" | "transcript" | null;
};

export type RetrievedChunk = {
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
  applied_platform?: "youtube" | "instagram" | null;
  applied_source_type?: "metadata" | "description" | "hook" | "transcript" | null;
  total_results: number;
  results: RetrievedChunk[];
};

export type ProjectRecord = {
  project_id: string;
  youtube_url: string;
  instagram_url: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ProjectDetailResponse = ProjectRecord & {
  youtube: VideoMetadata | null;
  instagram: VideoMetadata | null;
};

export type HealthResponse = {
  status: string;
  service?: string;
  environment?: string;
  message?: string;
};
