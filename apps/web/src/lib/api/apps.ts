import { api } from "../api";

export type AppAudience = "staff" | "customer";
/** unit = only staff of the owning unit see it; bank = every employee (owner-only setting) */
export type AppShareScope = "unit" | "bank";

export interface AppResponse {
  id: string;
  name: string;
  workflow_id: string | null;
  /** knowledge bases searched together for RAG, in the order they were picked */
  dataset_ids: string[];
  model_config_json: Record<string, any> | null;
  system_prompt: string | null;
  api_key: string;
  description: string | null;
  is_published: boolean;
  audience: AppAudience;
  embed_enabled: boolean;
  allowed_origins: string[];
  extension_enabled: boolean;
  extension_hosts: string[];
  widget_config: WidgetConfigInput;
  /** API-relative URL of the uploaded logo (null = default icon); prefix with apiAssetUrl() */
  logo_url: string | null;
  share_scope: AppShareScope;
  /** when on and tools are bound, answers go through the tool-calling agent */
  agent_enabled: boolean;
  tool_ids: string[];
  skill_ids: string[];
  skill_match_threshold: number;
  memory_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface RunResponse {
  id: string;
  app_id: string | null;
  workflow_id: string | null;
  conversation_id: string | null;
  status: string;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
}

export interface RunStepResponse {
  id: string;
  node_id: string;
  node_type: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  input_json: Record<string, any> | null;
  output_json: Record<string, any> | null;
}

export interface WidgetConfigInput {
  title?: string | null;
  subtitle?: string | null;
  greeting?: string | null;
  primary_color?: string;
  position?: "right" | "left";
  launcher_text?: string | null;
  suggestions?: string[];
  show_powered_by?: boolean;
  theme?: "light" | "dark" | "auto";
  disclaimer?: string | null;
}

export interface AppUpdate {
  name?: string;
  workflow_id?: string;
  /** replaces the whole set of bound knowledge bases */
  dataset_ids?: string[];
  model_config_json?: Record<string, any>;
  system_prompt?: string;
  description?: string;
  is_published?: boolean;
  audience?: AppAudience;
  embed_enabled?: boolean;
  allowed_origins?: string[];
  extension_enabled?: boolean;
  extension_hosts?: string[];
  widget_config?: WidgetConfigInput;
  share_scope?: AppShareScope;
  agent_enabled?: boolean;
  /** replaces the whole set of bound tools */
  tool_ids?: string[];
  skill_ids?: string[];
  skill_match_threshold?: number;
  memory_enabled?: boolean;
}

export function createApp(data: { name: string; workflow_id?: string; dataset_ids?: string[]; model_config_json?: Record<string, any>; system_prompt?: string; audience?: AppAudience; description?: string }) {
  return api.post<AppResponse>("/v1/apps", data);
}

export function listApps() {
  return api.get<AppResponse[]>("/v1/apps");
}

export function getApp(id: string) {
  return api.get<AppResponse>(`/v1/apps/${id}`);
}

export function updateApp(id: string, data: AppUpdate) {
  return api.patch<AppResponse>(`/v1/apps/${id}`, data);
}

export function deleteApp(id: string) {
  return api.delete(`/v1/apps/${id}`);
}

/** Upload a logo / avatar (PNG, JPG, WebP, GIF, ICO ≤ 1 MB or a script-free SVG). Saves immediately. */
export function uploadAppLogo(id: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return api.upload<AppResponse>(`/v1/apps/${id}/logo`, fd);
}

export function deleteAppLogo(id: string) {
  return api.delete<AppResponse>(`/v1/apps/${id}/logo`);
}

export function regenerateApiKey(id: string) {
  return api.post<AppResponse>(`/v1/apps/${id}/regenerate-key`);
}

export function listRuns(appId: string) {
  return api.get<RunResponse[]>(`/v1/apps/${appId}/runs`);
}

export function getRunSteps(runId: string) {
  return api.get<RunStepResponse[]>(`/v1/runs/${runId}/steps`);
}

/** One-line snippet a website owner pastes to get the chat bubble. */
export function embedSnippet(app: AppResponse): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `<script src="${origin}/widget.js" data-app="${app.id}" data-key="${app.api_key}" async></script>`;
}

/** Iframe URL used by the admin preview (our own origin is always an allowed ancestor). */
export function embedPreviewUrl(app: AppResponse): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/embed/${app.id}#k=${app.api_key}&o=${encodeURIComponent(origin)}&preview=1`;
}

/** Public link a customer opens for a customer-facing assistant. */
export function customerLink(app: AppResponse): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  // Key travels in the fragment so it never reaches server logs / Referer headers.
  return `${origin}/kh/${app.id}#k=${app.api_key}`;
}
