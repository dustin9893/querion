/**
 * Chat transport for the admin console's "Thử nghiệm hỏi đáp" page: an admin talks to an
 * assistant of the active unit exactly like staff/customers would (same answer pipeline,
 * guardrails and PII masking), but through workspace-scoped admin endpoints. Every answer
 * is logged in the audit trail with channel `admin_test`.
 */
import { getAccessToken, getActiveWorkspaceId } from "@/lib/api";
import { saveBlob, type ChatTransport } from "@/lib/chat/transport";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function adminTransport(appId: string): ChatTransport {
  const headers = (): Record<string, string> => {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    const token = getAccessToken();
    const ws = getActiveWorkspaceId();
    if (token) h["Authorization"] = `Bearer ${token}`;
    if (ws) h["X-Workspace-Id"] = ws;
    return h;
  };
  return {
    async loadMessages(conversationId) {
      const r = await fetch(`${API_BASE}/v1/apps/${appId}/test-conversations/${conversationId}/messages`, { headers: headers() });
      if (!r.ok) return null;
      const msgs = await r.json();
      return msgs.map((m: any) => ({ id: m.id, role: m.role, content: m.content, sources: m.sources || undefined, feedback: m.feedback || null }));
    },
    stream(message, conversationId) {
      return fetch(`${API_BASE}/v1/apps/${appId}/test-chat`, {
        method: "POST", headers: headers(), body: JSON.stringify({ message, conversation_id: conversationId }),
      });
    },
    approve(approvalId, approve) {
      return fetch(`${API_BASE}/v1/apps/${appId}/test-tool-approvals/${approvalId}`, {
        method: "POST", headers: headers(), body: JSON.stringify({ approve }),
      });
    },
    async feedback(messageId, rating, reason) {
      const r = await fetch(`${API_BASE}/v1/apps/${appId}/test-messages/${messageId}/feedback`, {
        method: "POST", headers: headers(), body: JSON.stringify({ rating, reason: reason || null }),
      });
      return r.ok;
    },
    downloadFile(artifactId, filename) {
      const h: Record<string, string> = {};
      const token = getAccessToken();
      const ws = getActiveWorkspaceId();
      if (token) h["Authorization"] = `Bearer ${token}`;
      if (ws) h["X-Workspace-Id"] = ws;
      return saveBlob(`${API_BASE}/v1/artifacts/${artifactId}/download`, h, filename);
    },
  };
}
