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
  extraction_status: "pending" | "extracting" | "ready" | "failed";
  error_message?: string | null;
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
