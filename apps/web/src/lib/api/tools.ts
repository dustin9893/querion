import { api } from "../api";

export type ToolKind = "http" | "builtin" | "mcp" | "report" | "export";
export type ToolShareScope = "unit" | "bank";

export interface ToolResponse {
  id: string;
  workspace_id: string;
  slug: string;
  name: string;
  description: string;
  kind: ToolKind;
  config: Record<string, any>;
  params_schema: Record<string, any>;
  /** the secret itself is never returned by the API */
  has_secret: boolean;
  requires_approval: boolean;
  allow_customer: boolean;
  share_scope: ToolShareScope;
  is_active: boolean;
  timeout_sec: number;
  /** false → visible only because another unit shared it bank-wide (read-only here) */
  own_unit: boolean;
  /** how many assistants have it bound */
  used_by: number;
  created_at: string;
  updated_at: string;
}

export interface BuiltinTool {
  fn: string;
  name: string;
  description: string;
  params_schema: Record<string, any>;
}

export interface ToolInput {
  slug?: string;
  name?: string;
  description?: string;
  kind?: ToolKind;
  config?: Record<string, any>;
  params_schema?: Record<string, any>;
  secret?: string | null;
  requires_approval?: boolean;
  allow_customer?: boolean;
  share_scope?: ToolShareScope;
  is_active?: boolean;
  timeout_sec?: number;
}

export function listTools() {
  return api.get<ToolResponse[]>("/v1/tools");
}

export function listBuiltins() {
  return api.get<BuiltinTool[]>("/v1/tools/builtins");
}

export function createTool(data: ToolInput) {
  return api.post<ToolResponse>("/v1/tools", data);
}

export function updateTool(id: string, data: ToolInput) {
  return api.patch<ToolResponse>(`/v1/tools/${id}`, data);
}

export function deleteTool(id: string) {
  return api.delete(`/v1/tools/${id}`);
}

/** Run the tool once with sample arguments (30 s: an endpoint may be slow). */
export function testTool(id: string, args: Record<string, any>) {
  return api.post<{ ok: boolean; result?: any; error?: string }>(`/v1/tools/${id}/test`, { args }, { timeout: 30000 });
}

export const KIND_LABEL: Record<ToolKind, string> = {
  http: "API nội bộ",
  builtin: "Tính toán sẵn có",
  mcp: "MCP server",
  report: "Báo cáo (xuất tệp)",
  export: "Xuất Excel từ hội thoại",
};
