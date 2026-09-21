import { api } from "../api";
import type { Source } from "../citations";
import type { UsageBucket } from "./usage";

export type AuditChannel = "staff" | "customer" | "admin_test" | "embed" | "extension";

export interface AuditRunRow {
  id: string;
  started_at: string;
  latency_ms: number | null;
  status: string;
  channel: AuditChannel;
  workspace_id: string | null;
  workspace_name: string | null;
  app_id: string | null;
  app_name: string | null;
  workflow_id: string | null;
  conversation_id: string | null;
  asked_by: string | null;
  asked_by_meta: string | null;
  client_origin: string | null;
  query_preview: string | null;
  answer_preview: string | null;
  error: string | null;
  feedback_rating: "up" | "down" | null;
  feedback_reason: string | null;
  step_count: number;
  /** model tokens spent on this answer (token_usage) */
  total_tokens: number;
}

export interface AuditStep {
  id: string;
  node_id: string;
  node_type: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  input_json: Record<string, any> | null;
  output_json: Record<string, any> | null;
}

export interface AuditRunDetail extends AuditRunRow {
  question: string | null;
  answer: string | null;
  sources: Source[] | null;
  steps: AuditStep[];
  /** tokens per component for this run */
  usage: UsageBucket[];
}

export interface AuditSummary {
  total_runs: number;
  runs_by_channel: Record<string, number>;
  avg_latency_ms: number | null;
  error_count: number;
  feedback_up: number;
  feedback_down: number;
  feedback_rate: number;
  top_documents: { filename: string; count: number }[];
}

export interface AuditFilters {
  workspaces: { id: string; name: string }[];
  apps: { id: string; name: string; workspace_id: string; audience: string }[];
  channels: AuditChannel[];
}

export interface AuditQuery {
  workspace_id?: string;
  app_id?: string;
  channel?: AuditChannel | "";
  rating?: "up" | "down" | "none" | "";
  status?: "completed" | "failed" | "running" | "blocked" | "";
  q?: string;
  days?: number;
  limit?: number;
}

function qs(params: Record<string, any>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function listAuditRuns(query: AuditQuery = {}) {
  return api.get<AuditRunRow[]>(`/v1/audit/runs${qs(query)}`, { timeout: 20000 });
}

export function getAuditRun(id: string) {
  return api.get<AuditRunDetail>(`/v1/audit/runs/${id}`);
}

export function getAuditSummary(params: { workspace_id?: string; days?: number } = {}) {
  return api.get<AuditSummary>(`/v1/audit/summary${qs(params)}`, { timeout: 20000 });
}

export function getAuditFilters() {
  return api.get<AuditFilters>("/v1/audit/filters");
}
