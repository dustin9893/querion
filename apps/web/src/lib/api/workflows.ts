import { api } from "../api";
import type { ArtifactResponse } from "./artifacts";

export interface WorkflowResponse {
  id: string;
  type: string;
  name: string;
  description: string | null;
  dataset_id: string | null;
  graph_json: GraphJSON;
  node_count: number;
  created_at: string;
  updated_at: string;
}

export interface GraphJSON {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
}

/** A parameter the workflow's input node declares — drives the run dialog, schedules and forms. */
export interface InputField {
  name: string;
  label?: string;
  type?: "string" | "text" | "number" | "date" | "select" | "boolean";
  required?: boolean;
  default?: any;
  options?: string[];
  description?: string;
}

export interface WorkflowRunRow {
  id: string;
  status: string;
  channel: string;
  started_at: string;
  ended_at: string | null;
  latency_ms: number | null;
  error: string | null;
  answer_preview: string | null;
  schedule_id?: string | null;
  artifacts: ArtifactResponse[];
}

export interface RunResult {
  answer: string;
  extracted_params: Record<string, any>;
  retriever_resources: Array<{
    chunk_id: string;
    content_preview: string;
    chunk_index: number;
    document_id: string;
    dataset_id: string;
    filename: string;
    score: number;
  }>;
  artifacts: Array<{ id?: string; filename?: string; title?: string; error?: string }>;
}

export function createWorkflow(name: string, type: string = "chatflow", description?: string, datasetId?: string) {
  return api.post<WorkflowResponse>("/v1/workflows", {
    name,
    type,
    description: description || "",
    dataset_id: datasetId || null,
    graph_json: { nodes: [], edges: [] },
  });
}

export function listWorkflows() {
  return api.get<WorkflowResponse[]>("/v1/workflows");
}

export function getWorkflow(id: string) {
  return api.get<WorkflowResponse>(`/v1/workflows/${id}`);
}

export function updateWorkflow(id: string, data: { name?: string; type?: string; description?: string; dataset_id?: string; graph_json?: GraphJSON }) {
  return api.patch<WorkflowResponse>(`/v1/workflows/${id}`, data);
}

export function deleteWorkflow(id: string) {
  return api.delete(`/v1/workflows/${id}`);
}

export function runWorkflow(id: string, query: string, inputs?: Record<string, any>) {
  return api.post<RunResult>(`/v1/workflows/${id}/run`, { query, inputs }, { timeout: 180000 });
}

/** Queue a report run on the jobs worker; follow it with listWorkflowRuns. */
export function runWorkflowJob(id: string, inputs?: Record<string, any>) {
  return api.post<{ run_id: string; job_id: string; status: string }>(
    `/v1/workflows/${id}/jobs`, { query: "report", inputs });
}

export function listWorkflowRuns(id: string, limit = 30) {
  return api.get<WorkflowRunRow[]>(`/v1/workflows/${id}/runs?limit=${limit}`);
}

/** Upload a .docx template for a render_document node; returns its storage key + placeholders. */
export function uploadWorkflowTemplate(id: string, file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return api.upload<{ template_key: string; filename: string; variables: string[] }>(
    `/v1/workflows/${id}/template`, fd);
}

/** The fields declared by the graph's input node (empty when the workflow takes a free question). */
export function inputFieldsOf(graph: GraphJSON | undefined): InputField[] {
  const input = graph?.nodes?.find((n) => n.type === "input");
  const fields = input?.data?.fields;
  return Array.isArray(fields) ? (fields as InputField[]) : [];
}
