/**
 * Chat transport cho Trợ lý Vận hành, bong bóng trong trang quản trị.
 *
 * Giống `adminTransport` ở chỗ dùng JWT quản trị, khác ở chỗ trợ lý này không thuộc đơn vị nào
 * của người dùng. Header `X-Workspace-Id` vẫn gửi kèm, nhưng chỉ để trợ lý biết **đang mở đơn vị
 * nào** khi cần liệt kê kho tri thức hay soạn luồng. Máy chủ không dùng header đó để cấp quyền.
 *
 * Mỗi lượt hỏi ghi vào nhật ký truy vấn với kênh `ops`.
 */
import { getAccessToken, getActiveWorkspaceId } from "@/lib/api";
import type { ChatTransport } from "@/lib/chat/transport";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function opsTransport(): ChatTransport {
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
      const r = await fetch(`${API_BASE}/v1/ops/conversations/${conversationId}/messages`, { headers: headers() });
      if (!r.ok) return null;
      const msgs = await r.json();
      return msgs.map((m: { id: string; role: string; content: string; sources?: unknown; feedback?: unknown }) => ({
        id: m.id, role: m.role, content: m.content,
        sources: (m.sources as never) || undefined,
        feedback: (m.feedback as never) || null,
      }));
    },
    stream(message, conversationId) {
      return fetch(`${API_BASE}/v1/ops/chat`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
          route: typeof window !== "undefined" ? window.location.pathname : null,
        }),
      });
    },
    async feedback(messageId, rating, reason) {
      const r = await fetch(`${API_BASE}/v1/ops/messages/${messageId}/feedback`, {
        method: "POST", headers: headers(), body: JSON.stringify({ rating, reason: reason || null }),
      });
      return r.ok;
    },
  };
}
