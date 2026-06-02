import type {
  ChatCitation,
  ChatStreamRequest,
  HealthResponse,
  IndexProjectResponse,
  ProjectCreateRequest,
  ProjectCreateResponse,
  ProjectDetailResponse,
  RetrieveProjectChunksRequest,
  RetrieveResponse,
  TranscriptPreviewResponse,
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

export async function extractProject(
  projectId: string,
): Promise<ProjectDetailResponse> {
  return request<ProjectDetailResponse>(`/api/projects/${projectId}/extract`, {
    method: "POST",
  });
}

export async function getProject(
  projectId: string,
): Promise<ProjectDetailResponse> {
  return request<ProjectDetailResponse>(`/api/projects/${projectId}`);
}

export async function getTranscriptPreview(
  projectId: string,
  platform: "youtube" | "instagram",
  limit = 5,
): Promise<TranscriptPreviewResponse> {
  const params = new URLSearchParams({
    platform,
    limit: String(limit),
  });

  return request<TranscriptPreviewResponse>(
    `/api/projects/${projectId}/transcripts?${params.toString()}`,
  );
}

export async function indexProject(
  projectId: string,
): Promise<IndexProjectResponse> {
  return request<IndexProjectResponse>(`/api/projects/${projectId}/index`, {
    method: "POST",
  });
}

export async function retrieveProjectChunks(
  projectId: string,
  payload: RetrieveProjectChunksRequest,
): Promise<RetrieveResponse> {
  return request<RetrieveResponse>(`/api/projects/${projectId}/retrieve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

type StreamChatHandlers = {
  onSession?: (sessionId: string) => void;
  onToken?: (text: string) => void;
  onCitations?: (citations: ChatCitation[]) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

type ParsedSseEvent = {
  event: string;
  data: unknown;
};

export async function streamChatResponse(
  projectId: string,
  payload: ChatStreamRequest,
  handlers: StreamChatHandlers,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/chat/stream`,
    {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  if (!response.body) {
    throw new Error("Chat stream was not available.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseBuffer(buffer);
    buffer = parsed.remaining;

    for (const event of parsed.events) {
      handleStreamEvent(event, handlers);
    }
  }

  buffer += decoder.decode();

  if (buffer.trim()) {
    for (const event of parseSseBuffer(`${buffer}\n\n`).events) {
      handleStreamEvent(event, handlers);
    }
  }
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

function parseSseBuffer(buffer: string): {
  events: ParsedSseEvent[];
  remaining: string;
} {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const remaining = parts.pop() ?? "";
  const events = parts
    .map(parseSseEvent)
    .filter((event): event is ParsedSseEvent => event !== null);

  return {
    events,
    remaining,
  };
}

function parseSseEvent(rawEvent: string): ParsedSseEvent | null {
  const lines = rawEvent.split("\n");
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  try {
    return {
      event: eventName,
      data: JSON.parse(dataLines.join("\n")) as unknown,
    };
  } catch {
    return {
      event: "error",
      data: {
        message: "Could not parse chat stream event.",
      },
    };
  }
}

function handleStreamEvent(
  event: ParsedSseEvent,
  handlers: StreamChatHandlers,
) {
  const data = event.data;

  if (event.event === "token") {
    const text = objectValue(data, "text");

    if (typeof text === "string") {
      handlers.onToken?.(text);
    }

    return;
  }

  if (event.event === "citations") {
    const citations = objectValue(data, "citations");

    if (Array.isArray(citations)) {
      handlers.onCitations?.(citations as ChatCitation[]);
    }

    return;
  }

  if (event.event === "done") {
    const sessionId = objectValue(data, "session_id");

    if (typeof sessionId === "string" && sessionId) {
      handlers.onSession?.(sessionId);
    }

    handlers.onDone?.();
    return;
  }

  if (event.event === "error") {
    const message = objectValue(data, "message");
    handlers.onError?.(
      typeof message === "string" && message
        ? message
        : "Could not stream chat response.",
    );
  }
}

function objectValue(data: unknown, key: string): unknown {
  if (!data || typeof data !== "object") {
    return null;
  }

  return (data as Record<string, unknown>)[key];
}
