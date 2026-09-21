import { api } from "../api";

/** One field of a business form. `source` says who fills it; `pii` keeps it away from the model. */
export interface FormField {
  name: string;
  label: string;
  type: "string" | "text" | "number" | "date" | "select" | "boolean";
  source: "user" | "tool" | "llm";
  required: boolean;
  pii: boolean;
  default?: any;
  options?: string[];
  description?: string;
  llm_prompt?: string;
}

export interface FormResponse {
  id: string;
  workspace_id: string;
  own_unit: boolean;
  name: string;
  description: string | null;
  fields: FormField[];
  template_filename: string | null;
  has_template: boolean;
  prefill_tool_id: string | null;
  prefill_arg: string | null;
  prefill_mapping: Record<string, string>;
  is_published: boolean;
  share_scope: "unit" | "bank";
  created_at: string;
  updated_at: string;
}

export interface FormInput {
  name?: string;
  description?: string;
  fields?: FormField[];
  prefill_tool_id?: string | null;
  prefill_arg?: string | null;
  prefill_mapping?: Record<string, string>;
  is_published?: boolean;
  share_scope?: "unit" | "bank";
}

export const FIELD_TYPE_LABEL: Record<string, string> = {
  string: "Chữ", text: "Đoạn văn", number: "Số", date: "Ngày", select: "Chọn", boolean: "Có/Không",
};

export const FIELD_SOURCE_LABEL: Record<string, string> = {
  user: "Cán bộ nhập", tool: "Điền sẵn từ hệ thống", llm: "AI gợi ý",
};

export function listForms() {
  return api.get<FormResponse[]>("/v1/forms");
}

export function createForm(data: FormInput & { name: string }) {
  return api.post<FormResponse>("/v1/forms", data);
}

export function updateForm(id: string, data: FormInput) {
  return api.patch<FormResponse>(`/v1/forms/${id}`, data);
}

export function deleteForm(id: string) {
  return api.delete(`/v1/forms/${id}`);
}

export function uploadFormTemplate(id: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return api.upload<FormResponse>(`/v1/forms/${id}/template`, fd);
}

/** Fill the form with test values and keep the .docx as an admin artifact. */
export function renderFormPreview(id: string, values: Record<string, any>) {
  return api.post<{ artifact_id: string; filename: string }>(`/v1/forms/${id}/render`, { values });
}
