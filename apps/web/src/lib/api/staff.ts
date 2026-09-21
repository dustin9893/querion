/**
 * Staff (bank employee) API client — separate auth flow from admin.
 * Token stored under different localStorage keys.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const STAFF_TOKEN_KEY = "querion-staff-token";
const STAFF_REFRESH_KEY = "querion-staff-refresh";

export interface EmployeeInfo {
  id: string;
  email: string;
  name: string;
  employee_code: string | null;
  branch: string | null;
  department: string | null;
  position: string | null;
  must_change_password: boolean;
  workspace_id?: string | null;
  workspace_name?: string | null;
}

export interface PublishedApp {
  id: string;
  name: string;
  description: string | null;
  logo_url?: string | null;
  workspace_id?: string;
  /** bank → shared with every unit by its owner */
  share_scope?: "unit" | "bank";
  /** false → visible only because it is shared bank-wide */
  own_unit?: boolean;
  /** configured in Admin → Trợ lý → Nhúng vào website (max 4) */
  suggestions?: string[];
  greeting?: string | null;
}

export interface WorkspaceAppsGroup {
  workspace_name: string;
  apps: PublishedApp[];
}

// --- Token management ---
let accessToken: string | null = null;

export function setStaffToken(token: string | null) {
  accessToken = token;
}

export function getStaffToken() {
  return accessToken;
}

async function staffFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(opts.headers as Record<string, string> || {}) };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// --- Auth ---
export async function staffLogin(email: string, password: string) {
  const data = await staffFetch<{ access_token: string; refresh_token: string; employee: EmployeeInfo }>("/v1/staff/login", {
    method: "POST", body: JSON.stringify({ email, password }),
  });
  accessToken = data.access_token;
  localStorage.setItem(STAFF_TOKEN_KEY, data.access_token);
  localStorage.setItem(STAFF_REFRESH_KEY, data.refresh_token);
  return data;
}

export async function staffRefresh(): Promise<boolean> {
  const rt = localStorage.getItem(STAFF_REFRESH_KEY);
  if (!rt) return false;
  try {
    const data = await staffFetch<{ access_token: string }>("/v1/staff/refresh", {
      method: "POST", body: JSON.stringify({ refresh_token: rt }),
    });
    accessToken = data.access_token;
    localStorage.setItem(STAFF_TOKEN_KEY, data.access_token);
    return true;
  } catch { return false; }
}

export async function staffMe() {
  return staffFetch<EmployeeInfo>("/v1/staff/me");
}

export async function staffChangePassword(newPassword: string) {
  return staffFetch<{ detail: string }>("/v1/staff/change-password", {
    method: "POST", body: JSON.stringify({ new_password: newPassword }),
  });
}

export function staffLogout() {
  accessToken = null;
  localStorage.removeItem(STAFF_TOKEN_KEY);
  localStorage.removeItem(STAFF_REFRESH_KEY);
}

export function restoreStaffToken(): boolean {
  const t = localStorage.getItem(STAFF_TOKEN_KEY);
  if (t) { accessToken = t; return true; }
  return false;
}

// --- Reports delivered to this employee ("Báo cáo của tôi") ---
export interface StaffReport {
  id: string;
  title: string | null;
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
  schedule_name: string | null;
  preview: string | null;
}

export async function listStaffReports(limit = 30) {
  return staffFetch<StaffReport[]>(`/v1/staff/reports?limit=${limit}`);
}

/** Download through the API with the staff token, then hand the blob to the browser. */
export async function downloadStaffReport(report: Pick<StaffReport, "id" | "filename">) {
  const res = await fetch(`${API_BASE}/v1/staff/reports/${report.id}/download`, {
    headers: { Authorization: `Bearer ${accessToken || localStorage.getItem(STAFF_TOKEN_KEY) || ""}` },
  });
  if (!res.ok) throw new Error(`Không tải được báo cáo (${res.status})`);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = report.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

// --- Business forms the unit published ---
export interface StaffFormField {
  name: string;
  label: string;
  type: "string" | "text" | "number" | "date" | "select" | "boolean";
  source: "user" | "tool" | "llm";
  required: boolean;
  pii: boolean;
  default?: any;
  options?: string[];
  description?: string;
}

export interface StaffForm {
  id: string;
  name: string;
  description: string | null;
  fields: StaffFormField[];
  has_prefill: boolean;
  prefill_label: string | null;
}

export async function listStaffForms() {
  return staffFetch<StaffForm[]>("/v1/staff/forms");
}

/** Fill the tool-sourced fields from one business code (mã hồ sơ). */
export async function prefillStaffForm(formId: string, key: string) {
  return staffFetch<{ values: Record<string, any> }>(`/v1/staff/forms/${formId}/prefill`, {
    method: "POST", body: JSON.stringify({ key }),
  });
}

/** Ask the model to draft one free-text field (PII fields are never sent). */
export async function suggestStaffFormField(formId: string, field: string, values: Record<string, any>) {
  return staffFetch<{ text: string }>(`/v1/staff/forms/${formId}/suggest`, {
    method: "POST", body: JSON.stringify({ field, values }),
  });
}

export async function submitStaffForm(formId: string, values: Record<string, any>) {
  return staffFetch<{ artifact_id: string; filename: string; title: string }>(`/v1/staff/forms/${formId}/submit`, {
    method: "POST", body: JSON.stringify({ values }),
  });
}

// --- Published assistants ---
export async function listPublishedApps() {
  return staffFetch<WorkspaceAppsGroup[]>("/v1/staff/apps");
}
