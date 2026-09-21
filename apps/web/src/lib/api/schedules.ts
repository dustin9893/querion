import { api } from "../api";

export interface ScheduleResponse {
  id: string;
  workspace_id: string;
  workflow_id: string;
  workflow_name: string | null;
  name: string;
  cron: string;
  /** human-readable cron, e.g. "07:30 các ngày làm việc (T2–T6)" */
  cron_label: string;
  timezone: string;
  inputs: Record<string, any>;
  enabled: boolean;
  /** empty = every employee of the unit sees the report */
  deliver_positions: string[];
  retention_days: number;
  next_run_at: string | null;
  last_enqueued_at: string | null;
  last_run_id: string | null;
  last_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleInput {
  workflow_id: string;
  name: string;
  cron: string;
  timezone?: string;
  inputs?: Record<string, any>;
  enabled?: boolean;
  deliver_positions?: string[];
  retention_days?: number;
}

export const POSITIONS = ["RM", "CA", "GDV", "OPS", "CCO", "KSV"] as const;

/** Presets the editor offers instead of making people write cron ("07:30" -> "30 7 * * 1-5"). */
const hhmm = (t: string) => {
  const [h, m] = (t || "07:30").split(":").map((x) => Number(x) || 0);
  return { h, m };
};

export const CRON_PRESETS: { label: string; cron: (time: string) => string }[] = [
  { label: "Hằng ngày", cron: (t) => `${hhmm(t).m} ${hhmm(t).h} * * *` },
  { label: "Ngày làm việc (T2–T6)", cron: (t) => `${hhmm(t).m} ${hhmm(t).h} * * 1-5` },
  { label: "Hằng tuần (thứ Hai)", cron: (t) => `${hhmm(t).m} ${hhmm(t).h} * * 1` },
  { label: "Ngày 1 hằng tháng", cron: (t) => `${hhmm(t).m} ${hhmm(t).h} 1 * *` },
];

export function listSchedules(workflowId?: string) {
  return api.get<ScheduleResponse[]>(`/v1/schedules${workflowId ? `?workflow_id=${workflowId}` : ""}`);
}

export function createSchedule(data: ScheduleInput) {
  return api.post<ScheduleResponse>("/v1/schedules", data);
}

export function updateSchedule(id: string, data: Partial<ScheduleInput>) {
  return api.patch<ScheduleResponse>(`/v1/schedules/${id}`, data);
}

export function deleteSchedule(id: string) {
  return api.delete(`/v1/schedules/${id}`);
}

export function runScheduleNow(id: string) {
  return api.post<{ run_id: string; job_id: string; status: string }>(`/v1/schedules/${id}/run-now`);
}

export function previewCron(cron: string, timezone = "Asia/Ho_Chi_Minh") {
  return api.get<{ cron_label: string; next_runs: string[] }>(
    `/v1/schedules/preview?cron=${encodeURIComponent(cron)}&timezone=${encodeURIComponent(timezone)}`);
}

/** Is the ticker process alive? If not, nothing fires and the page says so. */
export function schedulerStatus() {
  return api.get<{ running: boolean; last_heartbeat: string | null }>("/v1/schedules/status");
}
