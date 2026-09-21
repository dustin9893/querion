/**
 * Trợ lý Vận hành — bong bóng trong trang quản trị.
 *
 * Mọi quản trị viên đều thấy bong bóng; chỉ super admin đọc và ghi được cấu hình.
 * Máy chủ mới là chỗ cưỡng chế điều đó, đây chỉ là lớp gọi API.
 */
import { apiFetch } from "@/lib/api";

export interface OpsTip {
  id: string;
  text: string;
  /** chỉ hiện trên các trang bắt đầu bằng đường dẫn này */
  route?: string;
  /** bấm vào gợi ý thì mở chat với câu hỏi này điền sẵn */
  ask?: string;
  roles?: string[];
}

export interface OpsBubble {
  enabled: boolean;
  name?: string;
  greeting?: string;
  primary_color?: string;
  logo_url?: string | null;
  suggestions?: string[];
  tips?: OpsTip[];
  tip_interval_sec?: number;
  max_tips_per_session?: number;
  workflow_gen_enabled?: boolean;
}

export interface OpsConfig {
  enabled: boolean;
  audience_roles: string[];
  tips: OpsTip[];
  tip_interval_sec: number;
  max_tips_per_session: number;
  workflow_gen_enabled: boolean;
  assistant: {
    id: string;
    name: string;
    system_prompt: string;
    model: string;
    greeting: string;
  } | null;
  updated_at: string | null;
}

export type OpsConfigPatch = Partial<
  Pick<OpsConfig, "enabled" | "audience_roles" | "tips" | "tip_interval_sec" | "max_tips_per_session" | "workflow_gen_enabled">
> & { system_prompt?: string; model?: string; greeting?: string };

/** What the bubble needs to draw itself. `{enabled:false}` when it is off or hidden from this role. */
export function getOpsBubble(): Promise<OpsBubble> {
  return apiFetch<OpsBubble>("/v1/ops/bubble");
}

export function getOpsConfig(): Promise<OpsConfig> {
  return apiFetch<OpsConfig>("/v1/ops/config");
}

export function saveOpsConfig(patch: OpsConfigPatch): Promise<OpsConfig> {
  return apiFetch<OpsConfig>("/v1/ops/config", { method: "PUT", body: JSON.stringify(patch) });
}

/** A workflow the assistant drafted. Nothing is saved until the admin clicks create. */
export interface WorkflowDraft {
  ten: string;
  mo_ta: string;
  workspace_id: string;
  workflow_id: string | null;
  workflow_name: string | null;
  graph_json: { nodes: { id: string; type: string; data?: { label?: string } }[]; edges: unknown[] };
}
