/**
 * Chat transports — the only place that knows which API endpoints / headers a
 * front-end uses. `AssistantChat` is transport-agnostic so the same UI serves:
 *   - customers on the /kh page and inside the embedded widget (publishable X-App-Key)
 *   - staff inside the embedded widget (JWT, same endpoints as the /staff portal)
 *
 * When the UI runs inside an iframe on another website, `embedOrigin` is sent as
 * `X-Embed-Origin` so the compliance audit log records which site asked.
 */
import type { Source } from "@/lib/citations";

// Next inlines NEXT_PUBLIC_API_URL at build time; other bundlers (the browser extension is built
// with Vite) have no `process`, so guard it and let them set the base at runtime instead.
let API_BASE: string =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) || "http://localhost:8000";

/** Runtime override of the API base — the extension reads it from managed storage / options. */
export function configureTransport(opts: { apiBase?: string }) {
  if (opts.apiBase) API_BASE = opts.apiBase.replace(/\/+$/, "");
}
export function apiBase(): string { return API_BASE; }

/** API-relative asset path (e.g. `logo_url`) → absolute URL for <img src>. */
export function assetUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  return /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`;
}

export interface ChatMessageDTO {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  sources?: Source[] | null;
  feedback?: "up" | "down" | null;
}

export interface ChatTransport {
  /** Load an existing conversation; null → not found / not ours. */
  loadMessages(conversationId: string): Promise<ChatMessageDTO[] | null>;
  /** Start a streamed answer; returns the raw SSE Response (caller parses). */
  stream(message: string, conversationId: string | null): Promise<Response>;
  /** 👍 / 👎 on an assistant message. */
  feedback(messageId: string, rating: "up" | "down", reason?: string): Promise<boolean>;
  /** Approve or reject a tool the assistant wants to run; streams the rest of the answer.
   *  Absent on channels where tools never pause (customers). */
  approve?(approvalId: string, approve: boolean): Promise<Response>;
  /** Download a file the assistant produced (report / form). Absent on the customer channel,
   *  where assistants have no file-producing tools. */
  downloadFile?(artifactId: string, filename: string): Promise<void>;
}

/** Fetch with the channel's auth and hand the blob to the browser as a download. */
export async function saveBlob(url: string, headers: Record<string, string>, filename: string) {
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`Không tải được tệp (${res.status})`);
  const href = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10000);
}

function withEmbed(headers: Record<string, string>, embedOrigin?: string | null) {
  if (embedOrigin) headers["X-Embed-Origin"] = embedOrigin;
  return headers;
}

export function customerTransport(appId: string, apiKey: string, embedOrigin?: string | null): ChatTransport {
  const headers = () => withEmbed({ "Content-Type": "application/json", "X-App-Key": apiKey }, embedOrigin);
  return {
    async loadMessages(conversationId) {
      const r = await fetch(`${API_BASE}/v1/public/assistants/${appId}/conversations/${conversationId}/messages`, { headers: headers() });
      if (!r.ok) return null;
      const msgs = await r.json();
      return msgs.map((m: any) => ({ id: m.id, role: m.role, content: m.content, sources: m.sources || undefined }));
    },
    stream(message, conversationId) {
      return fetch(`${API_BASE}/v1/public/assistants/${appId}/chat`, {
        method: "POST", headers: headers(), body: JSON.stringify({ message, conversation_id: conversationId }),
      });
    },
    async feedback(messageId, rating, reason) {
      const r = await fetch(`${API_BASE}/v1/public/assistants/${appId}/messages/${messageId}/feedback`, {
        method: "POST", headers: headers(), body: JSON.stringify({ rating, reason: reason || null }),
      });
      return r.ok;
    },
  };
}

export function staffTransport(
  appId: string, getToken: () => string | null, embedOrigin?: string | null,
  /** extra request headers, e.g. `X-Page-Origin` from the browser extension (audit only) */
  extra?: Record<string, string>,
): ChatTransport {
  const headers = () => withEmbed({ "Content-Type": "application/json", Authorization: `Bearer ${getToken() || ""}`, ...(extra || {}) }, embedOrigin);
  return {
    async loadMessages(conversationId) {
      const r = await fetch(`${API_BASE}/v1/staff/conversations/${conversationId}/messages`, { headers: headers() });
      if (!r.ok) return null;
      const msgs = await r.json();
      return msgs.map((m: any) => ({ id: m.id, role: m.role, content: m.content, sources: m.sources || undefined, feedback: m.feedback || null }));
    },
    stream(message, conversationId) {
      return fetch(`${API_BASE}/v1/staff/apps/${appId}/chat`, {
        method: "POST", headers: headers(), body: JSON.stringify({ message, conversation_id: conversationId }),
      });
    },
    approve(approvalId, approve) {
      return fetch(`${API_BASE}/v1/staff/tool-approvals/${approvalId}`, {
        method: "POST", headers: headers(), body: JSON.stringify({ approve }),
      });
    },
    async feedback(messageId, rating, reason) {
      const r = await fetch(`${API_BASE}/v1/staff/messages/${messageId}/feedback`, {
        method: "POST", headers: headers(), body: JSON.stringify({ rating, reason: reason || null }),
      });
      return r.ok;
    },
    downloadFile(artifactId, filename) {
      return saveBlob(`${API_BASE}/v1/staff/reports/${artifactId}/download`,
                      { Authorization: `Bearer ${getToken() || ""}` }, filename);
    },
  };
}

/** Widget config as served by GET /v1/public/assistants/{id}/embed-config */
export interface WidgetConfig {
  title: string;
  subtitle?: string | null;
  greeting?: string | null;
  primary_color: string;
  position: "right" | "left";
  launcher_text?: string | null;
  suggestions: string[];
  show_powered_by: boolean;
  theme: "light" | "dark" | "auto";
  disclaimer?: string | null;
}

export interface EmbedConfig {
  id: string;
  name: string;
  description: string | null;
  audience: "staff" | "customer";
  embed_enabled: boolean;
  allowed_origins: string[];
  widget: WidgetConfig;
  logo_url?: string | null;
}

export async function fetchEmbedConfig(appId: string, apiKey: string): Promise<EmbedConfig | null> {
  const r = await fetch(`${API_BASE}/v1/public/assistants/${appId}/embed-config`, { headers: { "X-App-Key": apiKey } });
  if (!r.ok) return null;
  return r.json();
}
