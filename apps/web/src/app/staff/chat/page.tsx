"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  restoreStaffToken, staffMe, staffLogout, staffRefresh, downloadStaffReport,
  listPublishedApps, WorkspaceAppsGroup, PublishedApp, EmployeeInfo, STAFF_TOKEN_KEY,
} from "@/lib/api/staff";
import { useStaffSettings, getThemeVars } from "@/components/providers/StaffSettingsProvider";
import { BRAND_NAME } from "@/lib/brand";
import { sourceLabel, sourceBody, type Source } from "@/lib/citations";
import Markdown from "@/components/ui/Markdown";
import { apiAssetUrl } from "@/lib/api";
import { fileSize } from "@/components/chat/AssistantChat";
import { deleteMemory } from "@/lib/api/memory";

interface Conversation { id: string; app_id: string; title: string; message_count: number; }
interface ToolEvent { tool: string; label: string; status: "running" | "done" | "error" | "rejected"; }
interface ChatFile { id: string; filename: string; title?: string | null; size?: number | null; }
interface ApprovalRequest { approval_id: string; tool: string; label: string; args: Record<string, unknown>; decided?: "approved" | "rejected"; }
interface SkillEvent { id: string; slug: string; name: string; version?: string }
interface MemoryNote { id: string; text: string; category_label?: string }
interface ChatMessage { role: string; content: string; sources?: Source[]; id?: string; runId?: string; feedback?: "up" | "down" | null; tools?: ToolEvent[]; approval?: ApprovalRequest; files?: ChatFile[]; skills?: SkillEvent[]; memories?: MemoryNote[]; }

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const getToken = () => localStorage.getItem(STAFF_TOKEN_KEY);


export default function StaffChatPage() {
  const router = useRouter();
  const { theme, toggleTheme, locale, setLocale, t } = useStaffSettings();
  const vars = getThemeVars(theme);

  const [employee, setEmployee] = useState<EmployeeInfo | null>(null);
  const [groups, setGroups] = useState<WorkspaceAppsGroup[]>([]);
  const [selectedApp, setSelectedApp] = useState<PublishedApp | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      if (!restoreStaffToken()) { router.replace("/staff/login"); return; }
      try {
        const me = await staffMe();
        if (me.must_change_password) { router.replace("/staff/change-password"); return; }
        setEmployee(me);
        setGroups(await listPublishedApps());
      } catch {
        const ok = await staffRefresh();
        if (!ok) { router.replace("/staff/login"); return; }
        try {
          const me = await staffMe();
          setEmployee(me);
          setGroups(await listPublishedApps());
        } catch { router.replace("/staff/login"); }
      }
      setLoading(false);
    })();
  }, []); // eslint-disable-line

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const loadConversations = useCallback(async (appId: string) => {
    try {
      const res = await fetch(`${API_BASE}/v1/staff/apps/${appId}/conversations`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) setConversations(await res.json());
    } catch { /* silent */ }
  }, []);

  const loadMessages = useCallback(async (convId: string) => {
    try {
      const res = await fetch(`${API_BASE}/v1/staff/conversations/${convId}/messages`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        const msgs = await res.json();
        setMessages(msgs.map((m: any) => ({ id: m.id, runId: m.run_id || undefined, role: m.role, content: m.content, sources: m.sources || undefined, feedback: m.feedback || null })));
      }
    } catch { /* silent */ }
  }, []);

  const selectApp = async (app: PublishedApp) => {
    setSelectedApp(app);
    setActiveConvId(null);
    setMessages([]);
    await loadConversations(app.id);
  };

  const selectConversation = async (conv: Conversation) => {
    setActiveConvId(conv.id);
    await loadMessages(conv.id);
  };

  const startNewChat = () => { setActiveConvId(null); setMessages([]); };

  const deleteConversation = async (convId: string) => {
    try {
      await fetch(`${API_BASE}/v1/staff/conversations/${convId}`, {
        method: "DELETE", headers: { Authorization: `Bearer ${getToken()}` },
      });
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) { setActiveConvId(null); setMessages([]); }
    } catch { /* silent */ }
  };

  const updateLast = (patch: Partial<ChatMessage>) => {
    setMessages((prev) => {
      const u = [...prev];
      u[u.length - 1] = { ...u[u.length - 1], ...patch };
      return u;
    });
  };

  /** Read one SSE response into the last assistant bubble (chat and tool-approval share it). */
  const consumeStream = async (res: Response, seed = ""): Promise<{ text: string; paused: boolean }> => {
    const reader = res.body?.getReader();
    const decoder = new TextDecoder();
    let accumulated = seed, buffer = "", paused = false;
    const tools: ToolEvent[] = [];
    const files: ChatFile[] = [];
    const skills: SkillEvent[] = [];
    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ") || line.trim() === "data: [DONE]") continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === "token") { accumulated += data.content; updateLast({ content: accumulated }); }
          else if (data.type === "sources") updateLast({ sources: data.sources });
          else if (data.type === "notice") setPiiNotice(String(data.content || ""));
          else if (data.type === "message_saved") updateLast({ id: data.message_id, runId: data.run_id });
          else if (data.type === "conversation_id" && !activeConvId) setActiveConvId(data.conversation_id);
          else if (data.type === "title") {
            setConversations((prev) => prev.map((c) => (c.id === (activeConvId || data.conversation_id) ? { ...c, title: data.title } : c)));
          } else if (data.type === "tool_call") {
            tools.push({ tool: data.tool, label: data.label || data.tool, status: "running" });
            updateLast({ tools: [...tools] });
          } else if (data.type === "tool_result") {
            const hit = [...tools].reverse().find((t) => t.tool === data.tool && t.status === "running");
            if (hit) hit.status = data.status === "done" ? "done" : data.status === "rejected" ? "rejected" : "error";
            else tools.push({ tool: data.tool, label: data.label || data.tool, status: data.status === "done" ? "done" : "error" });
            updateLast({ tools: [...tools] });
          } else if (data.type === "artifact" && data.artifact_id) {
            files.push({ id: data.artifact_id, filename: data.filename || "bao-cao", title: data.title, size: data.size });
            updateLast({ files: [...files] });
          } else if (data.type === "skill" && data.skill?.id) {
            // Chip kỹ năng tách khỏi chip công cụ: "làm theo bí kíp nào" khác "gọi API nào".
            if (!skills.some((k) => k.id === data.skill.id)) {
              skills.push(data.skill as SkillEvent);
              updateLast({ skills: [...skills] });
            }
          } else if (data.type === "memory_saved" && Array.isArray(data.memories)) {
            updateLast({ memories: data.memories as MemoryNote[] });
          } else if (data.type === "tool_approval" && data.approval_id) {
            paused = true;
            updateLast({ approval: { approval_id: data.approval_id, tool: data.tool, label: data.label || data.tool, args: data.args || {} } });
          } else if (data.type === "error") {
            accumulated += (accumulated ? "\n\n" : "") + `⚠️ ${data.content}`;
            updateLast({ content: accumulated });
          }
        } catch { /* skip */ }
      }
    }
    return { text: accumulated, paused };
  };

  /** Cán bộ duyệt hoặc từ chối thao tác trợ lý muốn chạy; câu trả lời chạy tiếp ngay sau đó. */
  /** Xoá ngay bản ghi trợ lý vừa học. Sửa được trong một bấm, đúng lúc nó vừa học. */
  const undoMemories = async (msg: ChatMessage) => {
    await Promise.all((msg.memories || []).map((m) => deleteMemory(m.id).catch(() => null)));
    setMessages((prev) => prev.map((m) => (m === msg ? { ...m, memories: [] } : m)));
  };

  const decideApproval = async (msg: ChatMessage, approve: boolean) => {
    if (!msg.approval || sending) return;
    const id = msg.approval.approval_id;
    setMessages((prev) => prev.map((m) => (m.approval?.approval_id === id
      ? { ...m, approval: { ...m.approval, decided: approve ? "approved" : "rejected" } } : m)));
    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/v1/staff/tool-approvals/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ approve }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Không gửi được quyết định" }));
        updateLast({ content: `⚠️ ${err.detail}` });
      } else {
        await consumeStream(res);
      }
    } catch {
      updateLast({ content: "⚠️ Lỗi kết nối khi gửi quyết định." });
    }
    setSending(false);
  };

  const handleSend = async (text?: string) => {
    const userMsg = (text ?? input).trim();
    if (!userMsg || !selectedApp || sending) return;
    setInput("");
    setPiiNotice(null);
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setSending(true);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API_BASE}/v1/staff/apps/${selectedApp.id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ message: userMsg, conversation_id: activeConvId }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Something went wrong" }));
        updateLast({ content: `⚠️ ${err.detail}` });
        setSending(false);
        return;
      }

      const { text: accumulated, paused } = await consumeStream(res);

      if (!accumulated && !paused) {  // paused = waiting for the approval card, not an empty answer
        setMessages((prev) => {
          const u = [...prev];
          if (!u[u.length - 1].content) u[u.length - 1] = { ...u[u.length - 1], content: t("noResponse") };
          return u;
        });
      }
      if (selectedApp) loadConversations(selectedApp.id);
    } catch {
      updateLast({ content: t("connectionError") });
    }
    setSending(false);
  };

  const handleLogout = () => { staffLogout(); router.replace("/staff/login"); };

  // ---- feedback (👍 / 👎 + optional reason) ----
  const [piiNotice, setPiiNotice] = useState<string | null>(null);
  const [reasonFor, setReasonFor] = useState<string | null>(null); // message id awaiting a reason
  const [reasonText, setReasonText] = useState("");

  const sendFeedback = async (messageId: string, rating: "up" | "down", reason?: string) => {
    try {
      const res = await fetch(`${API_BASE}/v1/staff/messages/${messageId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ rating, reason: reason || null }),
      });
      if (res.ok) {
        setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, feedback: rating } : m)));
      }
    } catch { /* silent */ }
  };

  const onThumb = (m: ChatMessage, rating: "up" | "down") => {
    if (!m.id) return;
    if (rating === "up") { setReasonFor(null); sendFeedback(m.id, "up"); return; }
    // 👎 → ask for a short (optional) reason; a single request is sent on confirm/skip,
    // so a later "no reason" write can never overwrite the reason.
    setReasonFor(m.id);
    setReasonText("");
  };

  const submitReason = (messageId: string, skip = false) => {
    sendFeedback(messageId, "down", skip ? undefined : (reasonText.trim() || undefined));
    setReasonFor(null);
  };

  if (loading) return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: vars["--s-bg"] }}>
      <div className="animate-spin rounded-full h-6 w-6 border-2" style={{ borderColor: vars["--s-accent"], borderTopColor: "transparent" }} />
    </div>
  );

  const positionLine = [employee?.position, employee?.branch].filter(Boolean).join(" · ");

  return (
    <div style={{ minHeight: "100vh", display: "flex", background: vars["--s-bg"], color: vars["--s-text"], transition: "background 0.3s, color 0.3s" }}>
      {/* Sidebar */}
      <div style={{ width: 280, borderRight: `1px solid ${vars["--s-border"]}`, display: "flex", flexDirection: "column", background: vars["--s-bg-secondary"], transition: "background 0.3s" }}>
        <div className="px-4 pt-4 pb-2">
          <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: vars["--s-accent-text"] }}>{BRAND_NAME}</p>
        </div>
        <div className="px-4 pb-4" style={{ borderBottom: `1px solid ${vars["--s-border"]}` }}>
          <div className="flex items-center justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold truncate">{employee?.name}</p>
              <p className="text-[10px] truncate" style={{ color: vars["--s-text-muted"] }}>
                {employee?.employee_code ? `${employee.employee_code} · ` : ""}{positionLine || employee?.email}
              </p>
              {employee?.workspace_name && (
                <p className="text-[10px] truncate" style={{ color: vars["--s-accent-text"] }} data-testid="staff-unit">{employee.workspace_name}</p>
              )}
            </div>
            <button onClick={handleLogout} className="rounded-lg p-1.5 shrink-0" style={{ color: vars["--s-text-muted"] }} title={t("logout")}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 14H3.333C2.597 14 2 13.403 2 12.667V3.333C2 2.597 2.597 2 3.333 2H6M10.667 11.333L14 8L10.667 4.667M14 8H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </div>
        </div>

        {/* Reports inbox */}
        <button onClick={() => router.push("/staff/reports")}
          className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-left transition-all"
          style={{ borderBottom: `1px solid ${vars["--s-border"]}`, color: vars["--s-text-secondary"] }}
          data-testid="staff-reports-link">
          📄 Báo cáo của tôi
        </button>

        <button onClick={() => router.push("/staff/forms")}
          className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-left transition-all"
          style={{ borderBottom: `1px solid ${vars["--s-border"]}`, color: vars["--s-text-secondary"] }}
          data-testid="staff-forms-link">
          📝 Biểu mẫu
        </button>

        <button onClick={() => router.push("/staff/memory")}
          className="flex items-center gap-2 px-4 py-2.5 text-xs font-medium text-left transition-all"
          style={{ borderBottom: `1px solid ${vars["--s-border"]}`, color: vars["--s-text-secondary"] }}
          data-testid="staff-memory-link">
          🧠 Trợ lý nhớ gì về tôi
        </button>

        {/* Settings row: language + theme */}
        <div className="flex items-center justify-between px-4 py-2" style={{ borderBottom: `1px solid ${vars["--s-border"]}` }}>
          <button onClick={() => setLocale(locale === "vi" ? "en" : "vi")}
            className="text-[10px] font-bold uppercase rounded px-2 py-1 transition-all"
            style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
            {locale === "vi" ? "🇻🇳 VI" : "🇬🇧 EN"}
          </button>
          <button onClick={toggleTheme} className="rounded-lg p-1.5 transition-all"
            style={{ color: vars["--s-text-secondary"] }}
            title={theme === "dark" ? t("lightMode") : t("darkMode")}>
            {theme === "dark" ? (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 2V3M8 13V14M2 8H3M13 8H14M3.75 3.75L4.5 4.5M11.5 11.5L12.25 12.25M12.25 3.75L11.5 4.5M4.5 11.5L3.75 12.25" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M14 9.32A6 6 0 016.68 2a6 6 0 107.32 7.32z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            )}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {groups.length === 0 ? (
            <p className="text-xs text-center py-8" style={{ color: vars["--s-text-muted"] }}>{t("noApps")}</p>
          ) : groups.map((group) => (
            <div key={group.workspace_name}>
              <p className="text-[10px] font-bold uppercase tracking-wider px-2 mb-1.5" style={{ color: vars["--s-text-muted"] }}>
                {group.workspace_name}
              </p>
              <div className="space-y-1">
                {group.apps.map((app) => (
                  <button key={app.id} onClick={() => selectApp(app)}
                    className="w-full text-left rounded-lg px-3 py-2 text-sm transition-all"
                    style={{
                      background: selectedApp?.id === app.id ? vars["--s-accent-light"] : "transparent",
                      color: selectedApp?.id === app.id ? vars["--s-accent-text"] : vars["--s-text-secondary"],
                    }}>
                    <span className="flex items-center gap-2 min-w-0">
                      {app.logo_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={apiAssetUrl(app.logo_url) || ""} alt="" className="rounded-md shrink-0" style={{ width: 18, height: 18, objectFit: "cover" }} />
                      )}
                      <span className="font-medium truncate">{app.name}</span>
                      {app.share_scope === "bank" && !app.own_unit && (
                        <span className="shrink-0 rounded-full px-1.5 py-px text-[9px] font-bold uppercase tracking-wide"
                          style={{ background: "rgba(59,130,246,0.14)", color: "#2563eb" }}>{t("bankWide")}</span>
                      )}
                    </span>
                    {app.description && (
                      <p className="text-[10px] mt-0.5 truncate" style={{ color: vars["--s-text-muted"] }}>{app.description}</p>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {!selectedApp ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="rounded-full p-4 mx-auto w-fit mb-3" style={{ background: vars["--s-accent-light"] }}>
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ color: vars["--s-accent"] }}>
                  <path d="M8 10H24M8 16H20M8 22H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold">{t("selectApp")}</h2>
              <p className="text-sm mt-1" style={{ color: vars["--s-text-muted"] }}>{t("selectAppSubtitle")}</p>
            </div>
          </div>
        ) : (
          <>
            {/* Chat header */}
            <div className="px-5 py-3 flex items-center justify-between" style={{ borderBottom: `1px solid ${vars["--s-border"]}`, background: vars["--s-bg-secondary"], transition: "background 0.3s" }}>
              <div className="flex items-center gap-3 min-w-0">
                {selectedApp.logo_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={apiAssetUrl(selectedApp.logo_url) || ""} alt="" className="rounded-lg shrink-0" style={{ width: 30, height: 30, objectFit: "cover" }} />
                ) : (
                  <div className="rounded-lg p-1.5 shrink-0" style={{ background: vars["--s-accent-light"] }}>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ color: vars["--s-accent"] }}>
                      <path d="M3 4.5H13M3 8H10M3 11.5H8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                    </svg>
                  </div>
                )}
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold truncate">{selectedApp.name}</h3>
                  {selectedApp.description && (
                    <p className="text-[10px] truncate" style={{ color: vars["--s-text-muted"] }}>{selectedApp.description}</p>
                  )}
                </div>
              </div>
              <button onClick={startNewChat} className="rounded-lg px-3 py-1.5 text-xs font-medium shrink-0"
                style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
                {t("newChat")}
              </button>
            </div>

            {/* Conversation tabs */}
            {conversations.length > 0 && (
              <div className="flex gap-1 px-5 py-2 overflow-x-auto" style={{ borderBottom: `1px solid ${vars["--s-border"]}` }}>
                {conversations.map((conv) => (
                  <div key={conv.id} className="flex items-center gap-1 shrink-0">
                    <button onClick={() => selectConversation(conv)}
                      className="rounded-lg px-3 py-1 text-xs transition-all truncate"
                      style={{
                        maxWidth: 160,
                        background: activeConvId === conv.id ? vars["--s-accent-light"] : vars["--s-bg-tertiary"],
                        color: activeConvId === conv.id ? vars["--s-accent-text"] : vars["--s-text-muted"],
                        border: `1px solid ${activeConvId === conv.id ? vars["--s-accent"] + "30" : vars["--s-border"]}`,
                      }}>
                      {conv.title}
                    </button>
                    <button onClick={() => deleteConversation(conv.id)} className="text-[10px] px-1" style={{ color: vars["--s-text-muted"] }}>✕</button>
                  </div>
                ))}
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {messages.length === 0 && (
                <div className="py-10 max-w-2xl mx-auto">
                  {/* greeting + suggestions are the assistant's own widget config (Admin → Trợ lý → Nhúng vào website) */}
                  <p className="text-sm text-center mb-5" style={{ color: vars["--s-text-muted"] }} data-testid="staff-greeting">
                    {selectedApp.greeting ? selectedApp.greeting : <>{t("startConversation")} <strong>{selectedApp.name}</strong></>}
                  </p>
                  {(selectedApp.suggestions?.length ?? 0) > 0 && (
                    <>
                      <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: vars["--s-text-muted"] }}>{t("suggestedTitle")}</p>
                      <div className="grid gap-2 sm:grid-cols-2" data-testid="staff-suggestions">
                        {(selectedApp.suggestions || []).map((s) => (
                          <button key={s} onClick={() => handleSend(s)}
                            className="text-left text-xs rounded-lg px-3 py-2.5 transition-all"
                            style={{ background: vars["--s-bg-secondary"], color: vars["--s-text-secondary"], border: `1px solid ${vars["--s-border"]}` }}>
                            {s}
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className="max-w-[75%]">
                    <div className={`rounded-xl px-4 py-2.5 text-sm ${msg.role === "user" ? "whitespace-pre-wrap" : ""}`}
                      style={{
                        background: msg.role === "user" ? vars["--s-user-bubble"] : vars["--s-bot-bubble"],
                        color: msg.role === "user" ? vars["--s-user-text"] : vars["--s-bot-text"],
                        border: msg.role === "user" ? "none" : `1px solid ${vars["--s-border"]}`,
                        transition: "background 0.3s, color 0.3s",
                      }}>
                      {msg.role === "assistant" && (msg.tools?.length ?? 0) > 0 && (
                        <div className="mb-2 flex flex-wrap gap-1.5" data-testid="tool-chips">
                          {msg.tools!.map((tl, k) => (
                            <span key={`${tl.tool}-${k}`} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
                              style={{
                                background: tl.status === "error" ? "rgba(239,68,68,0.10)" : tl.status === "rejected" ? "rgba(120,120,120,0.12)" : vars["--s-accent-light"],
                                color: tl.status === "error" ? "#b91c1c" : tl.status === "rejected" ? vars["--s-text-muted"] : vars["--s-accent-text"],
                              }}>
                              <span aria-hidden>{tl.status === "running" ? "⏳" : tl.status === "done" ? "🔧" : tl.status === "rejected" ? "🚫" : "⚠️"}</span>
                              {tl.label}
                              {tl.status === "running" && " · đang chạy"}
                              {tl.status === "error" && " · lỗi"}
                              {tl.status === "rejected" && " · đã từ chối"}
                            </span>
                          ))}
                        </div>
                      )}
                      {msg.role === "assistant" && (msg.skills?.length ?? 0) > 0 && (
                        <div className="mb-2 flex flex-wrap gap-1.5" data-testid="skill-chips">
                          {msg.skills!.map((k) => (
                            <span key={k.id} data-testid="skill-chip"
                              title={`Kỹ năng ${k.slug}${k.version ? ` · ${k.version}` : ""}`}
                              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
                              style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
                              <span aria-hidden>🎯</span>{k.name}
                            </span>
                          ))}
                        </div>
                      )}
                      {msg.role === "assistant" && msg.content && !msg.content.startsWith("⚠️")
                        ? <Markdown accent={vars["--s-accent-text"]}>{msg.content}</Markdown>
                        : msg.content}
                      {msg.role === "assistant" && (msg.memories?.length ?? 0) > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]"
                             data-testid="memory-saved" style={{ color: vars["--s-text-muted"] }}>
                          <span aria-hidden>🧠</span>
                          <span>Đã ghi nhớ: {msg.memories!.map((m) => m.text).join(" · ")}</span>
                          <button onClick={() => undoMemories(msg)} className="underline">Hoàn tác</button>
                        </div>
                      )}
                      {msg.role === "assistant" && (msg.files?.length ?? 0) > 0 && (
                        <div className="mt-2.5 space-y-1.5" data-testid="chat-files">
                          {msg.files!.map((f) => (
                            <button key={f.id} data-testid="chat-file"
                              onClick={() => downloadStaffReport({ id: f.id, filename: f.filename })}
                              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left"
                              style={{ background: vars["--s-accent-light"], border: `1px solid ${vars["--s-accent"]}` }}>
                              <span aria-hidden className="text-base leading-none">⬇️</span>
                              <span className="min-w-0 flex-1">
                                <span className="block text-xs font-semibold truncate" style={{ color: vars["--s-text"] }}>{f.title || f.filename}</span>
                                <span className="block text-[11px] truncate" style={{ color: vars["--s-text-muted"] }}>{f.filename}{fileSize(f.size)}</span>
                              </span>
                              <span className="rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white shrink-0" style={{ background: vars["--s-accent"] }}>Tải về</span>
                            </button>
                          ))}
                        </div>
                      )}
                      {msg.role === "assistant" && msg.approval && (
                        <div className="mt-1 rounded-xl px-3 py-2.5 text-xs" data-testid="tool-approval"
                          style={{ background: "rgba(245,158,11,0.10)", border: "1px solid rgba(245,158,11,0.35)" }}>
                          <p className="font-semibold mb-1">Cần anh/chị xác nhận thao tác</p>
                          <p style={{ color: vars["--s-text-muted"] }}>Trợ lý muốn chạy <strong style={{ color: vars["--s-text"] }}>{msg.approval.label}</strong> với:</p>
                          <ul className="mt-1 mb-2">
                            {Object.entries(msg.approval.args).map(([k, v]) => (
                              <li key={k}>· {k}: <strong>{String(v)}</strong></li>
                            ))}
                          </ul>
                          {msg.approval.decided ? (
                            <p style={{ color: vars["--s-text-muted"] }}>{msg.approval.decided === "approved" ? "Anh/chị đã duyệt." : "Anh/chị đã từ chối."}</p>
                          ) : (
                            <div className="flex gap-2">
                              <button onClick={() => decideApproval(msg, true)} disabled={sending} data-testid="approve-tool"
                                className="rounded-lg px-3 py-1.5 font-medium text-white" style={{ background: "#16a34a" }}>Duyệt và chạy</button>
                              <button onClick={() => decideApproval(msg, false)} disabled={sending} data-testid="reject-tool"
                                className="rounded-lg px-3 py-1.5 font-medium" style={{ border: `1px solid ${vars["--s-border"]}`, color: vars["--s-text"] }}>Từ chối</button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    {msg.role === "assistant" && msg.id && msg.content && !msg.content.startsWith("⚠️") && (
                      <div className="mt-1.5 flex items-center gap-1.5">
                        <button onClick={() => onThumb(msg, "up")} title="Hữu ích"
                          className="rounded-md px-2 py-1 text-xs transition-all"
                          style={{ background: msg.feedback === "up" ? "rgba(34,197,94,0.15)" : "transparent", border: `1px solid ${msg.feedback === "up" ? "rgba(34,197,94,0.4)" : vars["--s-border"]}`, color: vars["--s-text-secondary"] }}>👍</button>
                        <button onClick={() => onThumb(msg, "down")} title="Chưa đúng / thiếu"
                          className="rounded-md px-2 py-1 text-xs transition-all"
                          style={{ background: msg.feedback === "down" ? "rgba(239,68,68,0.12)" : "transparent", border: `1px solid ${msg.feedback === "down" ? "rgba(239,68,68,0.4)" : vars["--s-border"]}`, color: vars["--s-text-secondary"] }}>👎</button>
                        {msg.feedback && <span className="text-[10px]" style={{ color: vars["--s-text-muted"] }}>Đã ghi nhận — cảm ơn anh/chị</span>}
                      </div>
                    )}
                    {msg.role === "assistant" && msg.id && reasonFor === msg.id && (
                      <div className="mt-1.5 flex gap-1.5">
                        <input value={reasonText} onChange={(e) => setReasonText(e.target.value)} autoFocus
                          onKeyDown={(e) => { if (e.key === "Enter") submitReason(msg.id!); if (e.key === "Escape") submitReason(msg.id!, true); }}
                          placeholder="Lý do (tuỳ chọn): sai điều khoản, thiếu trích dẫn, lỗi thời…"
                          className="flex-1 text-xs rounded-md px-2 py-1.5 outline-none"
                          style={{ background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}` }} />
                        <button onClick={() => submitReason(msg.id!)} className="text-xs rounded-md px-2 py-1.5" style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>Gửi</button>
                        <button onClick={() => submitReason(msg.id!, true)} className="text-xs rounded-md px-2 py-1.5" style={{ color: vars["--s-text-muted"], border: `1px solid ${vars["--s-border"]}` }}>Bỏ qua</button>
                      </div>
                    )}
                    {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2">
                        <p className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: vars["--s-text-muted"] }}>{t("sources")}</p>
                        <div className="flex flex-wrap gap-1.5">
                          {msg.sources.map((src, j) => (
                            <span key={src.chunk_id || j} title={sourceBody(src)}
                              className="text-[10px] rounded-md px-2 py-1"
                              style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"], border: `1px solid ${vars["--s-border"]}` }}>
                              <strong>[#{j}]</strong> {sourceLabel(src) || "Tài liệu"}
                              {typeof src.score === "number" && <span style={{ opacity: 0.7 }}> · {(src.score * 100).toFixed(0)}%</span>}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {sending && messages[messages.length - 1]?.content === "" && (
                <div className="flex justify-start">
                  <div className="rounded-xl px-4 py-2.5" style={{ background: vars["--s-bot-bubble"], border: `1px solid ${vars["--s-border"]}` }}>
                    <div className="flex gap-1">
                      <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: vars["--s-accent"], animationDelay: "0ms" }} />
                      <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: vars["--s-accent"], animationDelay: "150ms" }} />
                      <div className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: vars["--s-accent"], animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Input */}
            <div className="px-5 pt-3 pb-2" style={{ borderTop: `1px solid ${vars["--s-border"]}` }}>
              {piiNotice && (
                <div role="status" className="mb-2 flex items-start gap-2 rounded-lg px-3 py-2 text-[11px]" style={{ background: "rgba(245,158,11,0.12)", color: theme === "dark" ? "#fcd34d" : "#92400e", border: "1px solid rgba(245,158,11,0.35)" }}>
                  <span aria-hidden>🔒</span><span>{piiNotice}</span>
                </div>
              )}
              <div className="flex gap-2">
                <input value={input} onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                  placeholder={t("typeMessage")} autoFocus
                  className="flex-1 text-sm rounded-xl px-4 py-2.5 outline-none transition-all"
                  style={{ background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}` }} />
                <button onClick={() => handleSend()} disabled={sending || !input.trim()}
                  className="rounded-xl px-4 py-2.5 text-sm font-medium transition-all"
                  style={{ background: input.trim() ? "linear-gradient(135deg, #ee6d1f, #f59e0b)" : vars["--s-bg-tertiary"], color: input.trim() ? "#fff" : vars["--s-text-muted"] }}>
                  {t("send")}
                </button>
              </div>
              <p className="text-[10px] mt-2 text-center" style={{ color: vars["--s-text-muted"] }}>{t("disclaimer")}</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
