import type {
  HealthResponse,
  ProjectCreateRequest,
  ProjectCreateResponse,
  ProjectRecord,
} from "@/types/project";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function checkBackend(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function createProject(
  payload: ProjectCreateRequest,
): Promise<ProjectCreateResponse> {
  return request<ProjectCreateResponse>("/api/projects", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export async function getProject(projectId: string): Promise<ProjectRecord> {
  return request<ProjectRecord>(`/api/projects/${projectId}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    ...init,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return (await response.json()) as T;
}

async function getErrorMessage(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as unknown;
    const detail = extractDetail(data);

    if (detail) {
      return detail;
    }
  } catch {
    // Fall through to a generic HTTP message.
  }

  return `API returned HTTP ${response.status}`;
}

function extractDetail(data: unknown): string | null {
  if (!data || typeof data !== "object") {
    return null;
  }

  if ("message" in data && typeof data.message === "string") {
    return data.message;
  }

  if ("detail" in data && typeof data.detail === "string") {
    return data.detail;
  }

  if ("detail" in data && Array.isArray(data.detail)) {
    const messages = data.detail
      .map((item) => {
        if (
          item &&
          typeof item === "object" &&
          "msg" in item &&
          typeof item.msg === "string"
        ) {
          return item.msg;
        }

        return null;
      })
      .filter(Boolean);

    return messages.length > 0 ? messages.join(" ") : null;
  }

  return null;
}
