/**
 * Typed client for the Novel Editorial N24 API.
 *
 * The panel is served by the API itself (FastAPI static mount), so all
 * requests use same-origin relative paths. Every failure is surfaced as a
 * readable Error carrying the request path and HTTP status.
 */

import type { components, operations } from "./schema";

/**
 * Workspace creation body, taken from the generated OpenAPI types instead of
 * being hand-written a second time.
 */
export type CreateWorkspaceBody = components["schemas"]["CreateWorkspaceBody"];

/** Talk send body (POST /works/{id}/talk), from the generated OpenAPI types. */
export type TalkSendBody = components["schemas"]["TalkSendBody"];

/** Author empty-draft body (POST /works/{id}/drafts/new), generated type. */
export type DraftNewBody = components["schemas"]["DraftNewBody"];

/** Manual save body (PUT /works/{id}/drafts/{draft_id}/content), generated type. */
export type DraftSaveBody = components["schemas"]["DraftSaveBody"];

/** LLM generate body (POST /works/{id}/drafts), generated type. */
export type DraftGenerateBody = components["schemas"]["DraftGenerateBody"];

/** LLM revise body (POST /works/{id}/drafts/{draft_id}/revise), generated type. */
export type DraftReviseBody = components["schemas"]["DraftReviseBody"];

/** Corpus/feedback path plus the CLI's ``--apply`` flag (POST .../calibrate etc.). */
export type CorpusPathBody = components["schemas"]["CorpusPathBody"];

/** One whitelisted config key/value pair (PUT /config), generated type. */
export type ConfigWriteBody = components["schemas"]["ConfigWriteBody"];

/** Structure node bodies (add / patch / move), generated OpenAPI types. */
export type StructureAddBody = components["schemas"]["StructureAddBody"];
export type StructurePatchBody = components["schemas"]["StructurePatchBody"];
export type StructureMoveBody = components["schemas"]["StructureMoveBody"];

/** Outline write body (create without reason, revise with reason), generated type. */
export type OutlineWriteBody = components["schemas"]["OutlineWriteBody"];

/** Setting write body (add without setting_id, revise with setting_id + reason). */
export type SettingWriteBody = components["schemas"]["SettingWriteBody"];

/** Inspiration add body (POST /works/{id}/inspirations), generated type. */
export type InspirationAddBody = components["schemas"]["InspirationAddBody"];

export interface ConfigSnapshot {
  data_dir: string;
  config_path: string;
  llm_base_url: string;
  llm_model: string;
  log_level: string;
  quality_threshold: number;
  memory_decay_per_day: number;
  memory_rehearsal_boost: number;
  memory_archive_threshold: number;
  proactive_enabled: boolean;
  proactive_max_per_agent: number;
  freedom_dial: number;
  freedom_seed: number;
  motive_llm_enabled: boolean;
  embedding_backend: string;
  embedding_model: string;
  embedding_dim: number;
  embedding_top_k: number;
  api_host: string;
  api_port: number;
  panel_poll_interval: number;
  restart_required: boolean;
  message?: string;
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
  actor: string;
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

/**
 * One conversation item, marked and rendered like ``talk list`` (GET
 * /works/{id}/talk). The ``mark`` and ``line`` fields are exactly what the CLI
 * prints; the UI renders them structurally instead of as raw text.
 */
export interface TalkMessage {
  id: string;
  role: string;
  actor: string;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
  mark: string | null;
  line: string;
}

/**
 * Result of POST /works/{id}/talk. The send response carries the new messages
 * without the list-level ``mark``/``line`` enrichment; the UI refreshes via
 * GET afterwards, so those stay optional here.
 */
export interface TalkSentMessage {
  id: string;
  role: string;
  actor: string;
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
  mark?: string | null;
  line?: string;
}

export interface TalkSendResult {
  messages: TalkSentMessage[];
}

/**
 * Draft write responses (new / generate / save / revise) mirror the summary
 * plus the ``awaiting_decision`` flag the quality gate implies.
 */
export type DraftWriteResponse = DraftSummary & {
  awaiting_decision: boolean;
};

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

/** One outline version (GET /works/{id}/outline), mirroring ``outline show``. */
export interface Outline {
  id: string;
  workspace_id: string;
  version: number;
  content: string;
  reason: string | null;
  actor: string;
  created_at: string;
}

/** One setting entry with its latest version content (``setting list/show``). */
export interface SettingEntry {
  id: string;
  kind: string;
  name: string;
  content: string;
  source: string;
  current_version: number;
  created_at: string;
  updated_at: string;
}

/** One inspiration snippet (``inspiration list/show``). */
export interface Inspiration {
  id: string;
  workspace_id: string;
  kind: string;
  content: string;
  source: string;
  created_at: string;
  updated_at: string;
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

export interface WorkspaceSummary {
  id: string;
  title: string;
  genre: string;
  description: string;
  status: string;
  created_at: string;
}

export interface BandAgent {
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

export interface WorkspaceDetail extends WorkspaceSummary {
  band: BandAgent[];
}

export interface BandTemplate {
  name: string;
  description: string;
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

async function requestText(path: string, init?: RequestInit): Promise<string> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "text/plain");
  }
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw await toReadableError(response, path);
  }
  return response.text();
}

export function getConfig(): Promise<ConfigSnapshot> {
  return requestJson<ConfigSnapshot>("/config");
}

/** Write one whitelisted config key (PUT /config); restart the API to apply. */
export function updateConfig(body: ConfigWriteBody): Promise<ConfigSnapshot> {
  return requestJson<ConfigSnapshot>("/config", {
    method: "PUT",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

function parseContentDispositionFilename(disposition: string): string | null {
  const match =
    /filename\*=UTF-8''([^;]+)|filename="([^"]*)"|filename=([^;]+)/i.exec(
      disposition,
    );
  if (match === null) {
    return null;
  }
  const raw = match[1] ?? match[2] ?? match[3];
  if (raw === undefined || raw === "") {
    return null;
  }
  let filename = raw;
  if (match[1] !== undefined) {
    try {
      filename = decodeURIComponent(raw);
    } catch (error) {
      if (!(error instanceof URIError)) {
        throw error;
      }
    }
  }
  return filename.trim();
}

/**
 * Download one workspace as a verifiable ZIP archive (GET .../export). The
 * filename comes from Content-Disposition, falling back to the workspace id.
 */
export async function exportWorkspace(workspaceId: string): Promise<void> {
  const path = `${workspacePath(workspaceId)}/export`;
  const response = await fetch(path, {
    headers: new Headers({ Accept: "application/zip" }),
  });
  if (!response.ok) {
    throw await toReadableError(response, path);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename =
    parseContentDispositionFilename(disposition) ?? `${workspaceId}.zip`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(url);
  }
}

/**
 * Import an exported workspace ZIP as a brand-new workspace (POST /works/import,
 * multipart). The browser sets the multipart boundary; do not set Content-Type.
 */
export function importWorkspace(file: File): Promise<WorkspaceSummary> {
  const form = new FormData();
  form.append("file", file);
  return requestJson<WorkspaceSummary>("/works/import", {
    method: "POST",
    body: form,
  });
}

export function listWorks(): Promise<WorkspaceSummary[]> {
  return requestJson<WorkspaceSummary[]>("/works");
}

export function getWorkspace(workspaceId: string): Promise<WorkspaceDetail> {
  return requestJson<WorkspaceDetail>(workspacePath(workspaceId));
}

export function createWorkspace(
  body: CreateWorkspaceBody,
): Promise<WorkspaceSummary> {
  return requestJson<WorkspaceSummary>("/works", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

export function listTemplates(): Promise<BandTemplate[]> {
  return requestJson<BandTemplate[]>("/templates");
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

/** Send one message to the band (POST /works/{id}/talk, like ``talk send``). */
export function sendTalk(
  workspaceId: string,
  body: TalkSendBody,
): Promise<TalkSendResult> {
  return requestJson<TalkSendResult>(`${workspacePath(workspaceId)}/talk`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Conversation for one workspace (GET /works/{id}/talk, like ``talk list``). */
export function listTalk(workspaceId: string): Promise<TalkMessage[]> {
  return requestJson<TalkMessage[]>(`${workspacePath(workspaceId)}/talk`);
}

/** Create an empty author-owned draft (POST /works/{id}/drafts/new). */
export function createAuthorDraft(
  workspaceId: string,
  body: DraftNewBody,
): Promise<DraftWriteResponse> {
  return requestJson<DraftWriteResponse>(
    `${workspacePath(workspaceId)}/drafts/new`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    },
  );
}

/** Generate a draft version via the LLM (POST /works/{id}/drafts). */
export function generateDraft(
  workspaceId: string,
  body: DraftGenerateBody,
): Promise<DraftWriteResponse> {
  return requestJson<DraftWriteResponse>(`${workspacePath(workspaceId)}/drafts`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Save an author-written version (PUT /works/{id}/drafts/{draft_id}/content). */
export function saveDraftContent(
  workspaceId: string,
  draftId: string,
  body: DraftSaveBody,
): Promise<DraftWriteResponse> {
  return requestJson<DraftWriteResponse>(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}/content`,
    {
      method: "PUT",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    },
  );
}

/** Re-generate a draft as a new version (POST .../revise, like ``draft revise``). */
export function reviseDraft(
  workspaceId: string,
  draftId: string,
  body: DraftReviseBody,
): Promise<DraftWriteResponse> {
  return requestJson<DraftWriteResponse>(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}/revise`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    },
  );
}

export function getDraft(workspaceId: string, draftId: string): Promise<DraftDetail> {
  return requestJson<DraftDetail>(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}`,
  );
}

/** Query of GET /works/{id}/drafts/{draft_id}/diff, from the generated OpenAPI types. */
type DraftDiffQuery =
  operations["get_draft_diff_works__workspace_id__drafts__draft_id__diff_get"]["parameters"]["query"];

/**
 * Unified diff between two draft versions, consumed as plain text (GET
 * .../diff, like ``draft diff``). Identical versions resolve to
 * ``no differences``.
 */
export function getDraftDiff(
  workspaceId: string,
  draftId: string,
  query: DraftDiffQuery,
): Promise<string> {
  const params = new URLSearchParams({
    version_a: String(query.version_a),
    version_b: String(query.version_b),
  });
  return requestText(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}/diff?${params.toString()}`,
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

/** Add a structure node (POST /works/{id}/structure, like ``structure add``). */
export function createStructureNode(
  workspaceId: string,
  body: StructureAddBody,
): Promise<StructureNode> {
  return requestJson<StructureNode>(`${workspacePath(workspaceId)}/structure`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Rename a node or set its status (PATCH .../structure/{node_id}). */
export function patchStructureNode(
  workspaceId: string,
  nodeId: string,
  body: StructurePatchBody,
): Promise<StructureNode> {
  return requestJson<StructureNode>(
    `${workspacePath(workspaceId)}/structure/${encodeURIComponent(nodeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    },
  );
}

/** Move a node to the root or under another parent (POST .../move). */
export function moveStructureNode(
  workspaceId: string,
  nodeId: string,
  body: StructureMoveBody,
): Promise<StructureNode> {
  return requestJson<StructureNode>(
    `${workspacePath(workspaceId)}/structure/${encodeURIComponent(nodeId)}/move`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    },
  );
}

/** Remove a node and its subtree (DELETE .../structure/{node_id}). */
export function deleteStructureNode(
  workspaceId: string,
  nodeId: string,
): Promise<{ removed: number }> {
  return requestJson<{ removed: number }>(
    `${workspacePath(workspaceId)}/structure/${encodeURIComponent(nodeId)}`,
    { method: "DELETE" },
  );
}

/** Current outline version, or null when none (GET /works/{id}/outline). */
export function getOutline(workspaceId: string): Promise<Outline | null> {
  return requestJson<Outline | null>(
    `${workspacePath(workspaceId)}/outline`,
  );
}

/** Create (no reason) or revise (with reason) the outline (POST .../outline). */
export function writeOutline(
  workspaceId: string,
  body: OutlineWriteBody,
): Promise<Outline> {
  return requestJson<Outline>(`${workspacePath(workspaceId)}/outline`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Query of GET /works/{id}/settings, from the generated OpenAPI types. */
type SettingsListQuery =
  operations["get_workspace_settings_works__workspace_id__settings_get"]["parameters"]["query"];

/** Settings list, optionally filtered by kind label (GET /works/{id}/settings). */
export function listSettings(
  workspaceId: string,
  query: SettingsListQuery = {},
): Promise<SettingEntry[]> {
  const params = new URLSearchParams();
  if (query.kind) {
    params.set("kind", query.kind);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<SettingEntry[]>(
    `${workspacePath(workspaceId)}/settings${suffix}`,
  );
}

/** One setting with its latest version content (GET .../settings/{id}). */
export function getSetting(
  workspaceId: string,
  settingId: string,
): Promise<SettingEntry> {
  return requestJson<SettingEntry>(
    `${workspacePath(workspaceId)}/settings/${encodeURIComponent(settingId)}`,
  );
}

/** Add (no setting_id) or revise (setting_id + reason) a setting (POST .../settings). */
export function writeSetting(
  workspaceId: string,
  body: SettingWriteBody,
): Promise<SettingEntry> {
  return requestJson<SettingEntry>(`${workspacePath(workspaceId)}/settings`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Stale/same-name conflict report as plain text (GET .../settings/check). */
export function checkSettings(workspaceId: string): Promise<string> {
  return requestText(`${workspacePath(workspaceId)}/settings/check`);
}

/** Query of GET /works/{id}/inspirations, from the generated OpenAPI types. */
type InspirationsListQuery =
  operations["get_workspace_inspirations_works__workspace_id__inspirations_get"]["parameters"]["query"];

/** Inspirations, newest first, optionally filtered by kind / keyword. */
export function listInspirations(
  workspaceId: string,
  query: InspirationsListQuery = {},
): Promise<Inspiration[]> {
  const params = new URLSearchParams();
  if (query.kind) {
    params.set("kind", query.kind);
  }
  if (query.keyword) {
    params.set("keyword", query.keyword);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<Inspiration[]>(
    `${workspacePath(workspaceId)}/inspirations${suffix}`,
  );
}

/** One inspiration with its source (GET .../inspirations/{id}). */
export function getInspiration(
  workspaceId: string,
  inspirationId: string,
): Promise<Inspiration> {
  return requestJson<Inspiration>(
    `${workspacePath(workspaceId)}/inspirations/${encodeURIComponent(inspirationId)}`,
  );
}

/** Add one inspiration snippet (POST /works/{id}/inspirations). */
export function createInspiration(
  workspaceId: string,
  body: InspirationAddBody,
): Promise<Inspiration> {
  return requestJson<Inspiration>(
    `${workspacePath(workspaceId)}/inspirations`,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    },
  );
}

/** Remove one inspiration (DELETE .../inspirations/{id}). */
export function deleteInspiration(
  workspaceId: string,
  inspirationId: string,
): Promise<{ id: string; kind: string }> {
  return requestJson<{ id: string; kind: string }>(
    `${workspacePath(workspaceId)}/inspirations/${encodeURIComponent(inspirationId)}`,
    { method: "DELETE" },
  );
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

/** AI-flavor quality gate report (GET .../quality/check, like ``quality check``). */
export function getQualityCheck(
  workspaceId: string,
  draftId: string,
): Promise<string> {
  return requestText(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}/quality/check`,
  );
}

/** AI-flavor localization + rewrite suggestions (GET .../quality/explain). */
export function getQualityExplain(
  workspaceId: string,
  draftId: string,
): Promise<string> {
  return requestText(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}/quality/explain`,
  );
}

/** Contradiction report against settings/threads (GET .../consistency). */
export function getDraftConsistency(
  workspaceId: string,
  draftId: string,
): Promise<string> {
  return requestText(
    `${workspacePath(workspaceId)}/drafts/${encodeURIComponent(draftId)}/consistency`,
  );
}

/**
 * Corpus calibration report; ``apply`` writes the config threshold like the
 * CLI (POST /quality/calibrate).
 */
export function calibrateQuality(body: CorpusPathBody): Promise<string> {
  return requestText("/quality/calibrate", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Trial-reader feedback alignment report; ``apply`` writes config (POST
 * /quality/feedback).
 */
export function analyzeQualityFeedback(body: CorpusPathBody): Promise<string> {
  return requestText("/quality/feedback", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Learn a style description from reference texts (POST .../style/learn). */
export function learnStyle(
  workspaceId: string,
  body: CorpusPathBody,
): Promise<string> {
  return requestText(`${workspacePath(workspaceId)}/style/learn`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  });
}

/** Cross-chapter style drift report (GET .../style/drift, like ``style drift``). */
export function getStyleDrift(workspaceId: string): Promise<string> {
  return requestText(`${workspacePath(workspaceId)}/style/drift`);
}

/** Partner motives as CLI-aligned text (GET /works/{id}/motives). */
export function listMotives(
  workspaceId: string,
  agent?: string,
): Promise<string> {
  const params = new URLSearchParams();
  if (agent !== undefined && agent !== "") {
    params.set("agent", agent);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestText(`${workspacePath(workspaceId)}/motives${suffix}`);
}

/** Drop one motive; appends an author feedback trace (DELETE .../motives/{id}). */
export function dropMotive(
  workspaceId: string,
  motiveId: string,
): Promise<string> {
  return requestText(
    `${workspacePath(workspaceId)}/motives/${encodeURIComponent(motiveId)}`,
    { method: "DELETE" },
  );
}

/** Every partner's patience pool and state breakdowns (GET .../patience). */
export function getPatience(workspaceId: string): Promise<string> {
  return requestText(`${workspacePath(workspaceId)}/patience`);
}

/** Query of GET /works/{id}/behavior/timeline, from the generated types. */
export type BehaviorTimelineQuery =
  operations["get_workspace_behavior_timeline_works__workspace_id__behavior_timeline_get"]["parameters"]["query"];

/** Behavior traces oldest first, filtered by agent / kinds (GET .../timeline). */
export function getBehaviorTimeline(
  workspaceId: string,
  query: BehaviorTimelineQuery = {},
): Promise<string> {
  const params = new URLSearchParams();
  if (typeof query.agent === "string" && query.agent !== "") {
    params.set("agent", query.agent);
  }
  for (const kind of query.kind ?? []) {
    params.append("kind", kind);
  }
  if (query.limit !== undefined) {
    params.set("limit", String(query.limit));
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestText(
    `${workspacePath(workspaceId)}/behavior/timeline${suffix}`,
  );
}

/** Each partner's current behavior state (GET /works/{id}/behavior). */
export function getBehaviorState(workspaceId: string): Promise<string> {
  return requestText(`${workspacePath(workspaceId)}/behavior`);
}
