/**
 * Kỹ năng của trợ lý — bí kíp nghiệp vụ nạp khi cần.
 *
 * Trợ lý luôn "thấy" tên và mô tả của mọi kỹ năng, nhưng chỉ đọc toàn văn kỹ năng khớp câu hỏi.
 * Vì vậy trường `description` là thứ quyết định kích hoạt đúng hay nhầm, và giao diện chấm điểm
 * nó ngay lúc soạn qua trường `quality` do máy chủ trả về.
 */
import { api, apiFetch, getAccessToken, getActiveWorkspaceId } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface SkillQuality {
  level: "tot" | "tam" | "yeu";
  problems: string[];
  hints: string[];
}

/** Kỹ năng khác có mô tả gần giống, dễ bị mô hình chọn nhầm. */
export interface SkillOverlap {
  id: string;
  name: string;
  slug: string;
  score: number;
}

export interface Skill {
  id: string;
  workspace_id: string;
  slug: string;
  name: string;
  description: string;
  body: string;
  version: string;
  effective_from: string | null;
  status: "draft" | "published";
  share_scope: "unit" | "bank";
  allow_customer: boolean;
  preferred_dataset_ids: string[];
  allowed_tool_ids: string[];
  reference_document_ids: string[];
  app_count: number;
  own_unit: boolean;
  quality: SkillQuality | null;
  overlaps: SkillOverlap[];
  created_at: string;
  updated_at: string;
}

export type SkillDraft = Partial<
  Pick<Skill,
    | "slug" | "name" | "description" | "body" | "version" | "effective_from" | "status"
    | "share_scope" | "allow_customer" | "preferred_dataset_ids" | "allowed_tool_ids"
    | "reference_document_ids">
>;

export interface SkillTryResult {
  chosen: { id: string; slug: string; name: string } | null;
  best_score: number;
  threshold: number;
  scores: { id: string; slug: string; name: string; score: number }[];
  note?: string;
}

export const STATUS_LABEL: Record<string, string> = {
  draft: "Nháp",
  published: "Đã công bố",
};

export const QUALITY_LABEL: Record<string, string> = {
  tot: "Tốt",
  tam: "Tạm được",
  yeu: "Cần sửa",
};

export const QUALITY_COLOR: Record<string, string> = {
  tot: "#16a34a",
  tam: "#d97706",
  yeu: "#dc2626",
};

export function listSkills() {
  return api.get<Skill[]>("/v1/skills");
}

export function getSkill(id: string) {
  return api.get<Skill>(`/v1/skills/${id}`);
}

export function createSkill(data: SkillDraft) {
  return api.post<Skill>("/v1/skills", data);
}

export function updateSkill(id: string, data: SkillDraft) {
  return api.patch<Skill>(`/v1/skills/${id}`, data);
}

export function deleteSkill(id: string) {
  return api.delete(`/v1/skills/${id}`);
}

/** Khung thân bài gợi ý sẵn: năm mục phản ánh đúng thứ mô hình cần đọc. */
export function skillTemplate() {
  return api.get<{ body: string }>("/v1/skills/template");
}

/** Gõ một câu, xem kỹ năng nào sẽ được kích hoạt. Thử được trước khi gắn vào trợ lý. */
export function trySkills(query: string, appId?: string) {
  return api.post<SkillTryResult>("/v1/skills/try", { query, app_id: appId || null });
}

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  const token = getAccessToken();
  const ws = getActiveWorkspaceId();
  if (token) h["Authorization"] = `Bearer ${token}`;
  if (ws) h["X-Workspace-Id"] = ws;
  return h;
}

/** Tải một kỹ năng về dưới dạng SKILL.md đúng chuẩn mở, chạy được trên agent khác. */
export async function exportSkill(id: string, slug: string) {
  await download(`${API_BASE}/v1/skills/${id}/export`, `${slug}-SKILL.md`);
}

/** Tải cả bộ kỹ năng của đơn vị thành zip, mỗi kỹ năng một thư mục. */
export async function exportAllSkills() {
  await download(`${API_BASE}/v1/skills-export`, "ky-nang.zip");
}

async function download(url: string, filename: string) {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) throw new Error(`Không tải được (${res.status})`);
  const href = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

/** Nhập một SKILL.md hoặc zip nhiều kỹ năng. Kỹ năng nhập về luôn ở trạng thái nháp. */
export async function importSkills(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/v1/skills-import`, {
    method: "POST", headers: authHeaders(), body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `Không nhập được (${res.status})`);
  return data as { created: string[]; skipped: string[]; detail: string };
}

export { apiFetch };
