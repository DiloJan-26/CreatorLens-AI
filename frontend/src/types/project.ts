export type ProjectCreateRequest = {
  youtube_url: string;
  instagram_url: string;
};

export type ProjectCreateResponse = {
  project_id: string;
  status: string;
  message: string;
};

export type ProjectRecord = {
  project_id: string;
  youtube_url: string;
  instagram_url: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type HealthResponse = {
  status: string;
  service?: string;
  environment?: string;
  message?: string;
};
