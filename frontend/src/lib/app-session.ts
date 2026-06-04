"use client";

const PROJECT_CHANGED_EVENT = "creatorlens_project_changed";

let activeProjectId: string | null = null;
const chatSessionIds = new Map<string, string>();
const chatDrafts = new Map<string, string>();

export function getActiveProjectId(): string | null {
  return activeProjectId;
}

export function setActiveProjectId(projectId: string) {
  activeProjectId = projectId;
  dispatchProjectChanged();
}

export function clearActiveProjectId() {
  activeProjectId = null;
  chatSessionIds.clear();
  chatDrafts.clear();
  dispatchProjectChanged();
}

export function subscribeToActiveProject(
  callback: (projectId: string | null) => void,
): () => void {
  function handleProjectChanged() {
    callback(activeProjectId);
  }

  window.addEventListener(PROJECT_CHANGED_EVENT, handleProjectChanged);

  return () => {
    window.removeEventListener(PROJECT_CHANGED_EVENT, handleProjectChanged);
  };
}

export function getChatSessionId(projectId: string): string | null {
  return chatSessionIds.get(projectId) ?? null;
}

export function setChatSessionId(projectId: string, sessionId: string) {
  chatSessionIds.set(projectId, sessionId);
}

export function clearChatSessionId(projectId: string) {
  chatSessionIds.delete(projectId);
}

export function getChatDraft(projectId: string): string {
  return chatDrafts.get(projectId) ?? "";
}

export function setChatDraft(projectId: string, draft: string) {
  if (!draft.trim()) {
    chatDrafts.delete(projectId);
    return;
  }

  chatDrafts.set(projectId, draft);
}

function dispatchProjectChanged() {
  window.dispatchEvent(
    new CustomEvent(PROJECT_CHANGED_EVENT, {
      detail: {
        projectId: activeProjectId,
      },
    }),
  );
}
