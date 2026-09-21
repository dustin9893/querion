import { api } from "../api";

export type DatasetVisibility = "internal" | "public";

export interface DatasetResponse {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  visibility: DatasetVisibility;
  document_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentResponse {
  id: string;
  dataset_id: string;
  filename: string;
  content_type: string;
  size: number;
  status: "uploaded" | "indexing" | "ready" | "failed";
  chunk_count: number;
  error_message: string | null;
  doc_type: string | null;
  version: string | null;
  effective_from: string | null;
  /** false → kept and indexed, but skipped by AI retrieval on every channel */
  enabled: boolean;
  disabled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DatasetDetailResponse extends DatasetResponse {
  documents: DocumentResponse[];
}

/** Banking document types — keys map to locale `docType.*` in datasets.json */
export const DOC_TYPES = ["quy_trinh", "quy_dinh", "huong_dan", "san_pham", "bieu_phi", "mau_bieu", "faq"] as const;
export type DocType = (typeof DOC_TYPES)[number];

export interface DocumentMeta {
  doc_type?: string;
  version?: string;
  effective_from?: string;
}

export function createDataset(name: string, description?: string, visibility: DatasetVisibility = "internal") {
  return api.post<DatasetResponse>("/v1/datasets", { name, description, visibility });
}

export function updateDataset(id: string, patch: { name?: string; description?: string; visibility?: DatasetVisibility }) {
  return api.patch<DatasetResponse>(`/v1/datasets/${id}`, patch);
}

export function listDatasets() {
  return api.get<DatasetResponse[]>("/v1/datasets");
}

export function getDataset(id: string) {
  return api.get<DatasetDetailResponse>(`/v1/datasets/${id}`);
}

export function deleteDataset(id: string) {
  return api.delete(`/v1/datasets/${id}`);
}

export function getDocument(id: string) {
  return api.get<DocumentResponse>(`/v1/documents/${id}`);
}

export function updateDocumentMeta(id: string, meta: DocumentMeta) {
  return api.patch<DocumentResponse>(`/v1/documents/${id}`, meta);
}

export function setDocumentEnabled(id: string, enabled: boolean) {
  return api.patch<DocumentResponse>(`/v1/documents/${id}`, { enabled });
}

export function deleteDocument(id: string) {
  return api.delete(`/v1/documents/${id}`);
}

export function indexDocument(id: string) {
  return api.post<{ status: string; job_id: string }>(`/v1/documents/${id}/index`);
}

export interface ChunkResponse {
  id: string;
  chunk_index: number;
  content: string;
  content_preview: string;
}

export interface ChunksPageResponse {
  total: number;
  page: number;
  page_size: number;
  chunks: ChunkResponse[];
}

export function getDocumentChunks(docId: string, page = 1, pageSize = 20) {
  return api.get<ChunksPageResponse>(`/v1/documents/${docId}/chunks?page=${page}&page_size=${pageSize}`);
}

export function updateChunk(chunkId: string, content: string) {
  return api.patch<ChunkResponse & { re_embedded: boolean }>(`/v1/chunks/${chunkId}`, { content });
}
