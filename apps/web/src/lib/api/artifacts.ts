import { api, getAccessToken, getActiveWorkspaceId } from "../api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ArtifactResponse {
  id: string;
  workspace_id: string;
  run_id: string | null;
  workflow_id: string | null;
  schedule_id: string | null;
  kind: "report" | "form" | "export";
  audience: "admin" | "staff";
  title: string | null;
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
  expires_at: string | null;
}

export interface ArtifactDetail extends ArtifactResponse {
  /** Markdown/text preview shown without downloading the file */
  preview: string | null;
}

export function listArtifacts(params: { workflow_id?: string; run_id?: string; schedule_id?: string; kind?: string; days?: number } = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") q.set(k, String(v)); });
  return api.get<ArtifactResponse[]>(`/v1/artifacts?${q.toString()}`);
}

export function getArtifact(id: string) {
  return api.get<ArtifactDetail>(`/v1/artifacts/${id}`);
}

export function deleteArtifact(id: string) {
  return api.delete(`/v1/artifacts/${id}`);
}

/** Download through the API (the object store is never exposed), then hand the blob to the browser. */
export async function downloadArtifact(a: Pick<ArtifactResponse, "id" | "filename">) {
  const headers: Record<string, string> = {};
  const token = getAccessToken();
  const ws = getActiveWorkspaceId();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (ws) headers["X-Workspace-Id"] = ws;
  const res = await fetch(`${API_BASE_URL}/v1/artifacts/${a.id}/download`, { headers });
  if (!res.ok) throw new Error(`Không tải được tệp (${res.status})`);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = a.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
