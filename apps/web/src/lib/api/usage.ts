import { api } from "../api";

export interface UsageBucket {
  key: string | null;
  label: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  calls: number;
  /** calls whose provider sent no counts (tokens estimated from text length) */
  estimated_calls: number;
}

export interface UsageDay {
  day: string;
  total_tokens: number;
  by_component: Record<string, number>;
}

export interface UsageSummary {
  days: number;
  since: string;
  totals: UsageBucket;
  by_day: UsageDay[];
  by_component: UsageBucket[];
  by_purpose: UsageBucket[];
  by_channel: UsageBucket[];
  by_app: UsageBucket[];
  by_workspace: UsageBucket[];
  /** key = "provider · model", label = llm | embedding */
  by_model: UsageBucket[];
}

export interface UsageQuery {
  days: number;
  workspace_id?: string;
  app_id?: string;
  channel?: string;
  component?: string;
}

export function getUsageSummary(q: UsageQuery) {
  const params = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => { if (v !== undefined && v !== "") params.set(k, String(v)); });
  return api.get<UsageSummary>(`/v1/usage/summary?${params.toString()}`);
}

/** Order, label, colour and meaning of every metered component (services/usage.py COMPONENTS). */
export const COMPONENTS: { key: string; label: string; color: string; hint: string }[] = [
  { key: "answer", label: "Trả lời (RAG / LLM)", color: "#ee6d1f", hint: "Sinh câu trả lời từ tài liệu cho cán bộ, khách hàng, website nhúng, thử nghiệm" },
  { key: "agent", label: "Agent gọi công cụ", color: "#8b5cf6", hint: "Mỗi vòng mô hình quyết định gọi công cụ rồi tổng hợp kết quả" },
  { key: "workflow_llm", label: "Luồng xử lý · sinh trả lời", color: "#0ea5e9", hint: "Bước llm_generate trong luồng xử lý" },
  { key: "workflow_extract", label: "Luồng xử lý · phân loại", color: "#06b6d4", hint: "Bước parameter_extract (định tuyến, trích xuất tham số)" },
  { key: "form_suggest", label: "Gợi ý nội dung biểu mẫu", color: "#ec4899", hint: "AI soạn phần tự luận trong biểu mẫu (không gửi dữ liệu nhạy cảm)" },
  { key: "title", label: "Đặt tiêu đề hội thoại", color: "#94a3b8", hint: "Một lần gọi ngắn sau câu hỏi đầu tiên" },
  { key: "query_embedding", label: "Nhúng câu hỏi", color: "#22c55e", hint: "Embedding câu hỏi để tra cứu kho tri thức" },
  { key: "document_embedding", label: "Lập chỉ mục văn bản", color: "#84cc16", hint: "Embedding các đoạn khi tải lên / lập chỉ mục lại / sửa đoạn" },
];

export const CHANNEL_LABEL: Record<string, string> = {
  staff: "Cổng cán bộ", customer: "Trang khách hàng", embed: "Website nhúng", extension: "Browser extension", admin_test: "Admin thử nghiệm",
  retrieval_test: "Thử tra cứu", indexing: "Lập chỉ mục", admin_edit: "Sửa đoạn văn bản",
  report: "Báo cáo (chạy nền)", scheduled: "Báo cáo theo lịch", form: "Biểu mẫu",
};
