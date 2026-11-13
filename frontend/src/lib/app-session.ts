"use client";

const PROJECT_CHANGED_EVENT = "creatorlens_project_changed";
const ACTIVE_PROJECT_STORAGE_KEY = "creatorlens_active_project_id";

let activeProjectId: string | null = null;
const chatSessionIds = new Map<string, string>();
const chatDrafts = new Map<string, string>();
const comparisonObjectives = new Map<string, string>();

export function getActiveProjectId(): string | null {
  if (!activeProjectId && typeof window !== "undefined") {
    activeProjectId = window.localStorage.getItem(ACTIVE_PROJECT_STORAGE_KEY);
  }

  return activeProjectId;
}

export function setActiveProjectId(projectId: string) {
  activeProjectId = projectId;
  window.localStorage.setItem(ACTIVE_PROJECT_STORAGE_KEY, projectId);
  dispatchProjectChanged();
}

export function clearActiveProjectId() {
  activeProjectId = null;
  window.localStorage.removeItem(ACTIVE_PROJECT_STORAGE_KEY);
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
  return chatSessionIds.get(projectId) ?? readSession(`creatorlens_chat_${projectId}`);
}

export function setChatSessionId(projectId: string, sessionId: string) {
  chatSessionIds.set(projectId, sessionId);
  try { window.sessionStorage.setItem(`creatorlens_chat_${projectId}`, sessionId); } catch {}
}

export function clearChatSessionId(projectId: string) {
  chatSessionIds.delete(projectId);
  try { window.sessionStorage.removeItem(`creatorlens_chat_${projectId}`); } catch {}
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


function readSession(key: string): string | null {
  try { return typeof window === "undefined" ? null : window.sessionStorage.getItem(key); } catch { return null; }
}
export function getComparisonObjective(projectId: string): import("@/types/project").ComparisonObjective {
  const value = comparisonObjectives.get(projectId) ?? readSession(`creatorlens_objective_${projectId}`);
  return value === "reach" || value === "engagement" || value === "creative_quality" ? value : "balanced";
}
export function setComparisonObjective(projectId: string, objective: import("@/types/project").ComparisonObjective) {
  comparisonObjectives.set(projectId, objective);
  try { window.sessionStorage.setItem(`creatorlens_objective_${projectId}`, objective); } catch {}
  window.dispatchEvent(new CustomEvent("creatorlens_objective_changed", { detail: { projectId, objective } }));
}
