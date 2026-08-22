/**
 * Typed client for the Novel Editorial N24 API.
 *
 * The panel is served by the API itself (FastAPI static mount), so all
 * requests use same-origin relative paths. Every failure is surfaced as a
 * readable Error carrying the request path and HTTP status.
 */

export interface PanelConfig {
  panel_poll_interval: number;
}

export interface OverviewItem {
  workspace_id: string;
  title: string;
  genre: string;
  status: string;
  pending_count: number;
  structure: string;
  last_activity: string;
  created_at: string;
}

export interface Overview {
  overviews: OverviewItem[];
  total: number;
  skipped: number;
}

export interface EditorialEvent {
  id: string;
  workspace_id: string;
  type: string;
  time: string;
  actor: string;
  payload: Record<string, unknown>;
}

export interface GlobalEvents {
  events: EditorialEvent[];
  skipped: number;
}

export interface PendingDraft {
  id: string;
  title: string;
  status: string;
  current_version: number;
  updated_at: string;
}

export type DraftSummary = PendingDraft;

export interface DraftVersion {
  version: number;
  reason: string;
  created_at: string;
  content: string;
}

export interface DraftDetail {
  id: string;
  title: string;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
  versions: DraftVersion[];
}

export interface Review {
  id: string;
  role: string;
  actor: string;
  content: string;
  created_at: string;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  personality: string;
  stance: string;
  values: string;
  aesthetic: string;
  emotion_baseline: string;
  mood: string;
  work_habits: string;
  weaknesses: string;
  relationship_presets: string;
  private_motive: string;
  created_at: string;
}

export interface StyleAnchor {
  description: string;
  forbidden_words: string;
}

export interface StructureNode {
  id: string;
  kind: string;
  title: string;
  parent_id: string | null;
  sort_order: number;
  status: string;
  draft_id: string | null;
  created_at: string;
}

export interface DecisionBody {
  draft_id: string;
  action: "accept" | "reject" | "note";
  content?: string;
}

export interface DecisionResult {
  id: string;
  status: string;
}

function workspacePath(workspaceId: string): string {
  return `/works/${encodeURIComponent(workspaceId)}`;
}

async function toReadableError(response: Response, path: string): Promise<Error> {
  let detail = "";
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      detail = body.detail;
    }
  } catch {
    // Non-JSON error body: keep the generic readable message.
  }
  const suffix = detail ? `：${detail}` : "";
  return new Error(`请求失败：${response.status} ${path}${suffix}`);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw await toReadableError(response, path);
  }
  return (await response.json()) as T;
}

async function requestText(path: string): Promise<string> {
  const headers = new Headers();
  headers.set("Accept", "text/plain");
  const response = await fetch(path, { headers });
  if (!response.ok) {
    throw await toReadableError(response, path);
  }
  return response.text();
}

export function getConfig(): Promise<PanelConfig> {
  return requestJson<PanelConfig>("/config");
}

export function getOverview(): Promise<Overview> {
  return requestJson<Overview>("/overview");
}

export function getGlobalEvents(): Promise<GlobalEvents> {
  return requestJson<GlobalEvents>("/events");
}

export function getPending(workspaceId: string): Promise<PendingDraft[]> {
  return requestJson<PendingDraft[]>(`${workspacePath(workspaceId)}/pending`);
}

export function getDrafts(workspaceId: string): Promise<DraftSummary[]> {
  return requestJson<DraftSummary[]>(`${workspacePath(workspaceId)}/drafts`);
}

export function getDraft(workspaceId: string, draftId: string): Promise<DraftDetail> {
  return requestJson<DraftDetail>(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}`,
  );
}

export function getReviews(workspaceId: string, draftId: string): Promise<Review[]> {
  const query = new URLSearchParams({ draft_id: draftId });
  return requestJson<Review[]>(`${workspacePath(workspaceId)}/reviews?${query.toString()}`);
}

export function getInspect(workspaceId: string, keyword: string): Promise<string> {
  const query = new URLSearchParams({ keyword });
  return requestText(`${workspacePath(workspaceId)}/inspect?${query.toString()}`);
}

export function getLog(workspaceId: string): Promise<string> {
  return requestText(`${workspacePath(workspaceId)}/log`);
}

export function getStyle(workspaceId: string): Promise<StyleAnchor> {
  return requestJson<StyleAnchor>(`${workspacePath(workspaceId)}/style`);
}

export function getStructure(workspaceId: string): Promise<StructureNode[]> {
  return requestJson<StructureNode[]>(`${workspacePath(workspaceId)}/structure`);
}

export function postDecision(
  workspaceId: string,
  body: DecisionBody,
): Promise<DecisionResult> {
  return requestJson<DecisionResult>(`${workspacePath(workspaceId)}/decisions`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}
