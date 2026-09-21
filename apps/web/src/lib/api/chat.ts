import { api, getAccessToken, getActiveWorkspaceId } from "../api";

export interface ConversationResponse {
  id: string;
  dataset_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface MessageResponse {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Array<{
    chunk_id: string;
    content: string;
    content_preview: string;
    chunk_index: number;
    filename: string;
    score: number;
  }> | null;
  created_at: string;
}

export function createConversation(datasetId: string, title?: string) {
  return api.post<ConversationResponse>(`/v1/datasets/${datasetId}/conversations`, { title: title || "New Chat" });
}

export function listConversations(datasetId: string) {
  return api.get<ConversationResponse[]>(`/v1/datasets/${datasetId}/conversations`);
}

export function deleteConversation(id: string) {
  return api.delete(`/v1/conversations/${id}`);
}

export function getMessages(conversationId: string) {
  return api.get<MessageResponse[]>(`/v1/conversations/${conversationId}/messages`);
}

/**
 * Send a message and receive streaming SSE response.
 * Returns a ReadableStream for the SSE events.
 */
export async function sendMessageStream(conversationId: string, content: string): Promise<Response> {
  const token = getAccessToken();
  const wsId = getActiveWorkspaceId();

  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const res = await fetch(`${baseUrl}/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(wsId ? { "x-workspace-id": wsId } : {}),
    },
    body: JSON.stringify({ content }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res;
}
