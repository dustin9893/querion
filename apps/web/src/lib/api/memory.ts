/**
 * Bộ nhớ cá nhân của cán bộ — "Trợ lý nhớ gì về tôi".
 *
 * Người dùng không thấy được bộ nhớ thì cá nhân hoá giống rò rỉ hơn là tính năng, nên mọi dòng
 * phải xem, sửa, ghim và xoá được. Tạm dừng tách hẳn khỏi xoá sạch: phần lớn người muốn ngừng học
 * thêm chứ không muốn mất những gì đã có.
 */
import { STAFF_TOKEN_KEY } from "@/lib/api/staff";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface MemoryItem {
  id: string;
  category: string;
  category_label: string;
  text: string;
  pinned: boolean;
  created_at: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  conversation_id: string | null;
}

export interface MemoryPage {
  enabled: boolean;
  /** cán bộ tự tạm dừng học thêm; lưu ở máy chủ nên theo người qua mọi thiết bị */
  paused: boolean;
  retention_days: number;
  categories: Record<string, string>;
  items: MemoryItem[];
  profile: {
    name: string;
    employee_code: string | null;
    position: string | null;
    branch: string | null;
    department: string | null;
  };
  never_remembers: string[];
}

/** Thông báo lần đầu chỉ hiện một lần cho mỗi trình duyệt. */
const SEEN_NOTICE_KEY = "msbka-memory-notice-seen";

export function noticeSeen(): boolean {
  try { return localStorage.getItem(SEEN_NOTICE_KEY) === "1"; } catch { return true; }
}
export function markNoticeSeen() {
  try { localStorage.setItem(SEEN_NOTICE_KEY, "1"); } catch { /* ignore */ }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  try {
    const t = localStorage.getItem(STAFF_TOKEN_KEY);
    if (t) h["Authorization"] = `Bearer ${t}`;
  } catch { /* ignore */ }
  return h;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/v1/staff${path}`, { headers: headers(), ...init });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string })?.detail || `Lỗi ${res.status}`);
  return data as T;
}

export function getMemory() {
  return call<MemoryPage>("/memory");
}

export function updateMemory(id: string, patch: { text?: string; pinned?: boolean }) {
  return call<MemoryItem>(`/memory/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function deleteMemory(id: string) {
  return call<{ detail: string }>(`/memory/${id}`, { method: "DELETE" });
}

/** Ngừng học thêm nhưng giữ nguyên những gì đã nhớ. Khác hẳn xoá sạch. */
export function setMemoryPaused(paused: boolean) {
  return call<{ paused: boolean; detail: string }>("/memory/pause", {
    method: "POST", body: JSON.stringify({ paused }),
  });
}

export function clearMemory() {
  return call<{ detail: string; removed: number }>("/memory", { method: "DELETE" });
}

export const CATEGORY_ICON: Record<string, string> = {
  trinh_bay: "✍️",
  vai_tro: "🪪",
  boi_canh: "📌",
  thuat_ngu: "🔤",
};
