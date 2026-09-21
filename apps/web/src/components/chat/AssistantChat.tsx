"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Markdown from "@/components/ui/Markdown";
import { sourceLabel, sourceBody, type Source } from "@/lib/citations";
import type { ChatTransport, WidgetConfig } from "@/lib/chat/transport";

export interface ToolEvent {
  tool: string;
  label: string;
  status: "running" | "done" | "error" | "rejected";
}

export interface ChatFile {
  id: string;
  filename: string;
  title?: string | null;
  content_type?: string | null;
  size?: number | null;
}

export interface ApprovalRequest {
  approval_id: string;
  tool: string;
  label: string;
  args: Record<string, unknown>;
  decided?: "approved" | "rejected";
}

export interface UiMessage {
  id?: string;
  role: string;
  content: string;
  sources?: Source[];
  feedback?: "up" | "down" | null;
  /** tool calls the assistant made while producing this answer */
  tools?: ToolEvent[];
  /** set when the assistant paused and is waiting for the user to approve a tool */
  approval?: ApprovalRequest;
  /** files this answer produced (report / form), offered as download chips */
  files?: ChatFile[];
  /** workflow drafts the assistant proposed; rendered by whoever passes `renderExtra` */
  drafts?: unknown[];
  /** playbooks that shaped this answer */
  skills?: { id: string; slug: string; name: string; version?: string }[];
}

interface Props {
  transport: ChatTransport;
  widget: WidgetConfig;
  /** "page" = full /kh page, "embed" = compact panel inside the widget iframe */
  variant: "page" | "embed";
  /** localStorage key that remembers the conversation id (partitioned per embedding site) */
  storageKey: string;
  brandName: string;
  /** Called when an answer finishes while the host says the panel is hidden */
  onAnswer?: () => void;
  onClose?: () => void;
  /** Extra header content (e.g. staff name + logout) */
  headerExtra?: React.ReactNode;
  /** Ask the user for a short reason on 👎 (staff) */
  askReasonOnDown?: boolean;
  /** Absolute URL of the assistant's logo; replaces the default icon in the header */
  logoUrl?: string | null;
  /** Text to drop into the input (e.g. the selection on the page the extension bubble sits on).
   *  Each new value replaces the draft; the user still has to send it. */
  prefill?: string | null;
  /** Renders anything an answer carries beyond text, sources and files. The ops bubble uses it
   *  for workflow drafts; every other channel leaves it out and nothing is drawn. */
  renderExtra?: (message: UiMessage) => React.ReactNode;
  /** Show the "Nguồn (n)" button and the citation list. Default true.
   *  The ops assistant turns it off: it explains how to use the software, so a citation chip is
   *  noise the admin never clicks. Sources are still recorded in the audit log. */
  showSources?: boolean;
}

/* ---------- theme from primary colour ---------- */
function hexToRgb(hex: string): [number, number, number] {
  const m = hex.replace("#", "");
  const n = parseInt(m.length === 3 ? m.split("").map((c) => c + c).join("") : m, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function darken(hex: string, f = 0.75): string {
  const [r, g, b] = hexToRgb(hex).map((v) => Math.round(v * f));
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
function useTheme(widget: WidgetConfig) {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    if (widget.theme === "dark") { setDark(true); return; }
    if (widget.theme === "light") { setDark(false); return; }
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setDark(mq.matches);
    const h = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [widget.theme]);
  return useMemo(() => {
    const primary = widget.primary_color || "#ee6d1f";
    const [r, g, b] = hexToRgb(primary);
    const rgba = (a: number) => `rgba(${r},${g},${b},${a})`;
    return dark ? {
      dark, primary, primaryText: "#ffffff", accentText: primary, accentLight: rgba(0.18),
      bg: "#0b1220", card: "#111a2e", border: "rgba(255,255,255,0.08)", text: "#f1f5f9", muted: "#94a3b8",
      userBubble: rgba(0.22), userText: "#f8fafc", input: "rgba(255,255,255,0.06)",
    } : {
      dark, primary, primaryText: "#ffffff", accentText: darken(primary), accentLight: rgba(0.10),
      bg: "#f7f7f9", card: "#ffffff", border: "rgba(15,23,42,0.08)", text: "#0f172a", muted: "#64748b",
      userBubble: rgba(0.12), userText: darken(primary, 0.6), input: "#ffffff",
    };
  }, [dark, widget.primary_color]);
}

const DEFAULT_DISCLAIMER = "Thông tin chỉ mang tính tham khảo theo tài liệu đã công bố; kết quả phê duyệt do ngân hàng thẩm định.";

/** " · 12 KB" for the download row, or "" when the size is unknown. */
export function fileSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "";
  return bytes < 1024 ? ` · ${bytes} B` : ` · ${Math.round(bytes / 1024)} KB`;
}


export default function AssistantChat({
  transport, widget, variant, storageKey, brandName, onAnswer, onClose, headerExtra, askReasonOnDown,
  logoUrl, prefill, renderExtra, showSources = true,
}: Props) {
  const C = useTheme(widget);
  const embed = variant === "embed";

  const [convId, setConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [openSources, setOpenSources] = useState<Record<number, boolean>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [reasonFor, setReasonFor] = useState<string | null>(null);
  const [reasonText, setReasonText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // restore conversation (storage may be blocked in third-party context → in-memory only)
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem(storageKey); } catch { /* blocked */ }
    if (!saved) return;
    (async () => {
      const msgs = await transport.loadMessages(saved!);
      if (msgs) {
        setMessages(msgs.map((m) => ({ id: m.id, role: m.role, content: m.content, sources: m.sources || undefined, feedback: m.feedback || null })));
        setConvId(saved);
      } else {
        try { localStorage.removeItem(storageKey); } catch { /* ignore */ }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);
  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    if (prefill) { setInput(prefill); inputRef.current?.focus(); }
  }, [prefill]);

  const updateLast = useCallback((patch: Partial<UiMessage>) =>
    setMessages((prev) => { const u = [...prev]; u[u.length - 1] = { ...u[u.length - 1], ...patch }; return u; }), []);

  /** Read one SSE response into the last assistant bubble. `seed` keeps text already shown. */
  const consume = async (res: Response, seed = ""): Promise<{ text: string; paused: boolean }> => {
    const reader = res.body?.getReader();
    const decoder = new TextDecoder();
    let acc = seed, buffer = "", paused = false;
    const tools: ToolEvent[] = [];
    const files: ChatFile[] = [];
    const drafts: unknown[] = [];
    const skills: { id: string; slug: string; name: string; version?: string }[] = [];
    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n"); buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ") || line.trim() === "data: [DONE]") continue;
        try {
          const d = JSON.parse(line.slice(6));
          if (d.type === "token") { acc += d.content; updateLast({ content: acc }); }
          else if (d.type === "sources") updateLast({ sources: d.sources });
          else if (d.type === "notice") setNotice(String(d.content || ""));
          else if (d.type === "message_saved") updateLast({ id: d.message_id });
          else if (d.type === "conversation_id") { setConvId(d.conversation_id); try { localStorage.setItem(storageKey, d.conversation_id); } catch { /* ignore */ } }
          else if (d.type === "tool_call") {
            tools.push({ tool: d.tool, label: d.label || d.tool, status: "running" });
            updateLast({ tools: [...tools] });
          } else if (d.type === "tool_result") {
            const hit = [...tools].reverse().find((t) => t.tool === d.tool && t.status === "running");
            if (hit) hit.status = d.status === "done" ? "done" : d.status === "rejected" ? "rejected" : "error";
            else tools.push({ tool: d.tool, label: d.label || d.tool, status: d.status === "done" ? "done" : "error" });
            updateLast({ tools: [...tools] });
          } else if (d.type === "artifact" && d.artifact_id) {
            files.push({ id: d.artifact_id, filename: d.filename || "bao-cao", title: d.title,
                         content_type: d.content_type, size: d.size });
            updateLast({ files: [...files] });
          } else if (d.type === "skill" && d.skill?.id) {
            // Chip kỹ năng tách khỏi chip công cụ: "trợ lý làm theo bí kíp nào" là thông tin khác
            // hẳn "trợ lý gọi API nào", và người đọc cần phân biệt được.
            if (!skills.some((k) => k.id === d.skill.id)) {
              skills.push({ id: d.skill.id, slug: d.skill.slug, name: d.skill.name, version: d.skill.version });
              updateLast({ skills: [...skills] });
            }
          } else if (d.type === "workflow_draft" && d.draft) {
            drafts.push(d.draft);
            updateLast({ drafts: [...drafts] });
          } else if (d.type === "tool_approval" && d.approval_id) {
            paused = true;
            updateLast({ approval: { approval_id: d.approval_id, tool: d.tool, label: d.label || d.tool, args: d.args || {} } });
          } else if (d.type === "error") { acc += (acc ? "\n\n" : "") + `⚠️ ${d.content}`; updateLast({ content: acc }); }
        } catch { /* skip */ }
      }
    }
    return { text: acc, paused };
  };

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || sending) return;
    setInput("");
    setNotice(null);
    setMessages((prev) => [...prev, { role: "user", content: msg }, { role: "assistant", content: "" }]);
    setSending(true);
    try {
      const res = await transport.stream(msg, convId);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Có lỗi xảy ra" }));
        const detail = res.status === 429 ? (err.detail || "Bạn gửi quá nhiều câu hỏi, vui lòng thử lại sau.") : (err.detail || `Lỗi ${res.status}`);
        updateLast({ content: `⚠️ ${detail}` });
        setSending(false);
        return;
      }
      const { text: acc, paused } = await consume(res);
      if (!acc && !paused) setMessages((prev) => { const u = [...prev]; if (!u[u.length - 1].content) u[u.length - 1] = { ...u[u.length - 1], content: "Không nhận được phản hồi." }; return u; });
      else if (acc) onAnswer?.();
    } catch {
      updateLast({ content: "⚠️ Lỗi kết nối. Vui lòng thử lại." });
    }
    setSending(false);
    inputRef.current?.focus();
  };

  /** Staff approves or rejects a tool the assistant wants to run; the answer then continues. */
  const decide = async (m: UiMessage, approve: boolean) => {
    if (!m.approval || !transport.approve || sending) return;
    const approvalId = m.approval.approval_id;
    setMessages((prev) => prev.map((x) => (x.approval?.approval_id === approvalId
      ? { ...x, approval: { ...x.approval, decided: approve ? "approved" : "rejected" } } : x)));
    setSending(true);
    try {
      const res = await transport.approve(approvalId, approve);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Không gửi được quyết định" }));
        updateLast({ content: `⚠️ ${err.detail || `Lỗi ${res.status}`}` });
      } else {
        const { text } = await consume(res, "");
        if (text) onAnswer?.();
      }
    } catch {
      updateLast({ content: "⚠️ Lỗi kết nối khi gửi quyết định." });
    }
    setSending(false);
  };

  const rate = async (m: UiMessage, rating: "up" | "down", reason?: string) => {
    if (!m.id) return;
    const ok = await transport.feedback(m.id, rating, reason);
    if (ok) setMessages((prev) => prev.map((x) => (x.id === m.id ? { ...x, feedback: rating } : x)));
  };
  const onThumb = (m: UiMessage, rating: "up" | "down") => {
    if (!m.id) return;
    if (rating === "down" && askReasonOnDown) { setReasonFor(m.id); setReasonText(""); return; }
    rate(m, rating);
  };

  const newChat = () => {
    setConvId(null); setMessages([]); setOpenSources({});
    try { localStorage.removeItem(storageKey); } catch { /* ignore */ }
    inputRef.current?.focus();
  };

  const suggestions = (widget.suggestions || []).slice(0, 4);
  const disclaimer = widget.disclaimer || DEFAULT_DISCLAIMER;
  const bubbleMax = embed ? "max-w-[88%]" : "max-w-[85%] sm:max-w-[75%]";

  return (
    <div style={{ height: "100%", minHeight: embed ? "100%" : "100vh", background: C.bg, color: C.text, display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header style={{ background: embed ? C.primary : C.card, color: embed ? C.primaryText : C.text, borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
        <div className={`${embed ? "" : "mx-auto max-w-3xl"} flex items-center justify-between gap-2 px-4 py-3`}>
          <div className="flex items-center gap-3 min-w-0">
            {logoUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logoUrl} alt="" aria-hidden="true" className="rounded-full shrink-0" data-testid="assistant-logo"
                style={{ width: embed ? 34 : 36, height: embed ? 34 : 36, objectFit: "cover", background: embed ? "rgba(255,255,255,0.92)" : C.accentLight }} />
            )}
            {!logoUrl && !embed && (
              <div className="rounded-xl p-2 shrink-0" style={{ background: C.accentLight }}>
                <svg width="20" height="20" viewBox="0 0 28 28" fill="none" style={{ color: C.primary }}>
                  <path d="M4 11L14 5L24 11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M6 11V21M11 11V21M17 11V21M22 11V21" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                  <path d="M4 23H24" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </div>
            )}
            {!logoUrl && embed && (
              <div className="rounded-full shrink-0 flex items-center justify-center" style={{ width: 34, height: 34, background: "rgba(255,255,255,0.2)" }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" style={{ color: "#fff" }}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.2 3.4c-.5.4-1.3 0-1.3-.6V16A2.5 2.5 0 0 1 4 13.5v-8Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round"/><path d="M8 8.5h8M8 11.5h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
              </div>
            )}
            <div className="min-w-0">
              {!embed && <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: C.accentText }}>{brandName}</p>}
              <h1 className={`${embed ? "text-sm" : "text-base"} font-semibold truncate`}>{widget.title}</h1>
              {widget.subtitle && <p className="text-xs truncate" style={{ color: embed ? "rgba(255,255,255,0.85)" : C.muted }}>{widget.subtitle}</p>}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {headerExtra}
            {messages.length > 0 && (
              <button onClick={newChat} title="Hội thoại mới" aria-label="Hội thoại mới" className="rounded-lg p-1.5 text-xs font-medium"
                style={{ background: embed ? "rgba(255,255,255,0.18)" : C.accentLight, color: embed ? "#fff" : C.accentText }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/></svg>
              </button>
            )}
            {embed && onClose && (
              <button onClick={onClose} title="Thu nhỏ" aria-label="Thu nhỏ" className="rounded-lg p-1.5" style={{ background: "rgba(255,255,255,0.18)", color: "#fff" }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Messages */}
      <main className={`${embed ? "" : "mx-auto max-w-3xl w-full"} flex-1 overflow-y-auto px-4`} aria-live="polite">
        <div className="space-y-3 py-4">
          {messages.length === 0 && (
            <div className={embed ? "" : "py-6"}>
              <div className="rounded-2xl p-4 mb-4" style={{ background: C.card, border: `1px solid ${C.border}` }}>
                <p className="text-sm">{widget.greeting || `Xin chào! Tôi là ${widget.title}.`}</p>
                <p className="text-xs mt-2" style={{ color: C.muted }}>Vui lòng không nhập mật khẩu, mã OTP, số thẻ hay thông tin cá nhân nhạy cảm.</p>
              </div>
              {suggestions.length > 0 && (
                <>
                  <p className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: C.muted }}>Gợi ý câu hỏi</p>
                  <div className={`grid gap-2 ${embed ? "" : "sm:grid-cols-2"}`}>
                    {suggestions.map((s) => (
                      <button key={s} onClick={() => send(s)} className="text-left text-xs rounded-lg px-3 py-2.5 transition-colors"
                        style={{ background: C.card, border: `1px solid ${C.border}`, color: C.text }}>{s}</button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
          {messages.map((m, i) => {
            const isErr = m.content.startsWith("⚠️");
            const n = showSources ? (m.sources?.length || 0) : 0;
            return (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={bubbleMax}>
                  <div className={`rounded-2xl px-4 py-2.5 text-sm ${m.role === "user" ? "whitespace-pre-wrap" : ""}`}
                    style={{
                      background: m.role === "user" ? C.userBubble : C.card,
                      color: m.role === "user" ? C.userText : C.text,
                      border: m.role === "user" ? "none" : `1px solid ${C.border}`,
                    }}>
                    {m.role === "assistant" && (m.tools?.length ?? 0) > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1.5" data-testid="tool-chips">
                        {m.tools!.map((t, k) => (
                          <span key={`${t.tool}-${k}`} className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
                            style={{
                              background: t.status === "error" ? "rgba(239,68,68,0.10)" : t.status === "rejected" ? "rgba(120,120,120,0.12)" : C.accentLight,
                              color: t.status === "error" ? "#b91c1c" : t.status === "rejected" ? C.muted : C.accentText,
                            }}>
                            <span aria-hidden>{t.status === "running" ? "⏳" : t.status === "done" ? "🔧" : t.status === "rejected" ? "🚫" : "⚠️"}</span>
                            {t.label}
                            {t.status === "running" && " · đang chạy"}
                            {t.status === "error" && " · lỗi"}
                            {t.status === "rejected" && " · đã từ chối"}
                          </span>
                        ))}
                      </div>
                    )}
                    {m.role === "assistant" && m.content && !isErr
                      ? <Markdown accent={C.accentText}>{m.content}</Markdown>
                      : (m.content || (sending && i === messages.length - 1 && !m.approval ? <Typing color={C.primary} /> : ""))}
                    {m.role === "assistant" && (m.files?.length ?? 0) > 0 && transport.downloadFile && (
                      <div className="mt-2.5 space-y-1.5" data-testid="chat-files">
                        {m.files!.map((f) => (
                          <button key={f.id} data-testid="chat-file"
                            onClick={() => transport.downloadFile!(f.id, f.filename).catch(() => setNotice("Không tải được tệp"))}
                            className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left"
                            style={{ background: C.accentLight, border: `1px solid ${C.primary}` }}>
                            <span aria-hidden className="text-base leading-none">⬇️</span>
                            <span className="min-w-0 flex-1">
                              <span className="block text-xs font-semibold truncate" style={{ color: C.text }}>{f.title || f.filename}</span>
                              <span className="block text-[11px] truncate" style={{ color: C.muted }}>{f.filename}{fileSize(f.size)}</span>
                            </span>
                            <span className="rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white shrink-0" style={{ background: C.primary }}>Tải về</span>
                          </button>
                        ))}
                      </div>
                    )}
                    {m.role === "assistant" && (m.skills?.length ?? 0) > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5" data-testid="skill-chips">
                        {m.skills!.map((k) => (
                          <span key={k.id} data-testid="skill-chip" title={`Kỹ năng ${k.slug}${k.version ? ` · ${k.version}` : ""}`}
                            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]"
                            style={{ background: C.accentLight, color: C.accentText }}>
                            <span aria-hidden>🎯</span>{k.name}
                          </span>
                        ))}
                      </div>
                    )}
                    {m.role === "assistant" && renderExtra?.(m)}
                    {m.role === "assistant" && m.approval && (
                      <div className="mt-1 rounded-xl px-3 py-2.5 text-xs" data-testid="tool-approval"
                        style={{ background: "rgba(245,158,11,0.10)", border: "1px solid rgba(245,158,11,0.35)" }}>
                        <p className="font-semibold mb-1" style={{ color: C.text }}>Cần bạn xác nhận thao tác</p>
                        <p style={{ color: C.muted }}>Trợ lý muốn chạy <strong style={{ color: C.text }}>{m.approval.label}</strong> với:</p>
                        <ul className="mt-1 mb-2" style={{ color: C.text }}>
                          {Object.entries(m.approval.args).map(([k, v]) => (
                            <li key={k}>· {k}: <strong>{String(v)}</strong></li>
                          ))}
                        </ul>
                        {m.approval.decided ? (
                          <p style={{ color: C.muted }}>{m.approval.decided === "approved" ? "Bạn đã duyệt." : "Bạn đã từ chối."}</p>
                        ) : (
                          <div className="flex gap-2">
                            <button onClick={() => decide(m, true)} disabled={sending} data-testid="approve-tool"
                              className="rounded-lg px-3 py-1.5 font-medium text-white" style={{ background: "#16a34a" }}>Duyệt và chạy</button>
                            <button onClick={() => decide(m, false)} disabled={sending} data-testid="reject-tool"
                              className="rounded-lg px-3 py-1.5 font-medium" style={{ border: `1px solid ${C.border}`, color: C.text }}>Từ chối</button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  {m.role === "assistant" && m.id && m.content && !isErr && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                      <button onClick={() => onThumb(m, "up")} aria-label="Hữu ích" className="rounded-md px-2 py-1" style={{ background: m.feedback === "up" ? "rgba(34,197,94,0.15)" : C.card, border: `1px solid ${C.border}` }}>👍</button>
                      <button onClick={() => onThumb(m, "down")} aria-label="Chưa đúng" className="rounded-md px-2 py-1" style={{ background: m.feedback === "down" ? "rgba(239,68,68,0.12)" : C.card, border: `1px solid ${C.border}` }}>👎</button>
                      {m.feedback && <span style={{ color: C.muted }}>Cảm ơn phản hồi của bạn</span>}
                      {n > 0 && (
                        <button onClick={() => setOpenSources((o) => ({ ...o, [i]: !o[i] }))} className="rounded-md px-2 py-1 ml-auto" style={{ background: C.accentLight, color: C.accentText }}>
                          Nguồn ({n}) {openSources[i] ? "▴" : "▾"}
                        </button>
                      )}
                    </div>
                  )}
                  {m.role === "assistant" && m.id && reasonFor === m.id && (
                    <div className="mt-1.5 flex gap-1.5">
                      <input value={reasonText} onChange={(e) => setReasonText(e.target.value)} autoFocus
                        onKeyDown={(e) => { if (e.key === "Enter") { rate(m, "down", reasonText.trim() || undefined); setReasonFor(null); } if (e.key === "Escape") { rate(m, "down"); setReasonFor(null); } }}
                        placeholder="Lý do (tuỳ chọn): sai điều khoản, thiếu trích dẫn…"
                        className="flex-1 text-xs rounded-md px-2 py-1.5 outline-none" style={{ background: C.input, color: C.text, border: `1px solid ${C.border}` }} />
                      <button onClick={() => { rate(m, "down", reasonText.trim() || undefined); setReasonFor(null); }} className="text-xs rounded-md px-2 py-1.5" style={{ background: C.accentLight, color: C.accentText }}>Gửi</button>
                    </div>
                  )}
                  {m.role === "assistant" && n > 0 && (!embed || openSources[i]) && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {m.sources!.map((s, j) => (
                        <span key={s.chunk_id || j} title={sourceBody(s)} className="text-[10px] rounded-md px-2 py-1"
                          style={{ background: C.accentLight, color: C.accentText, border: `1px solid ${C.border}` }}>
                          <strong>[#{j}]</strong> {sourceLabel(s) || "Tài liệu"}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>
      </main>

      {/* Input */}
      <div className={`${embed ? "" : "mx-auto max-w-3xl w-full"} px-4 pt-2 pb-3`} style={{ background: C.bg, borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
        {notice && (
          <div role="status" className="mb-2 flex items-start gap-2 rounded-lg px-3 py-2 text-[11px]" style={{ background: "rgba(245,158,11,0.12)", color: C.dark ? "#fcd34d" : "#92400e", border: "1px solid rgba(245,158,11,0.35)" }}>
            <span aria-hidden>🔒</span><span>{notice}</span>
          </div>
        )}
        <div className="flex gap-2">
          <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Nhập câu hỏi của bạn..." aria-label="Câu hỏi"
            className="flex-1 text-sm rounded-xl px-4 py-2.5 outline-none"
            style={{ background: C.input, border: `1px solid ${C.border}`, color: C.text }} />
          <button onClick={() => send()} disabled={sending || !input.trim()} aria-label="Gửi"
            className="rounded-xl px-4 py-2.5 text-sm font-semibold"
            style={{ background: input.trim() && !sending ? C.primary : (C.dark ? "rgba(255,255,255,0.08)" : "#e5e7eb"), color: input.trim() && !sending ? C.primaryText : C.muted }}>
            Gửi
          </button>
        </div>
        <p className="text-[10px] mt-2 text-center leading-snug" style={{ color: C.muted }}>
          {disclaimer}{widget.show_powered_by && <> · Powered by <strong>{brandName}</strong></>}
        </p>
      </div>
    </div>
  );
}

function Typing({ color }: { color: string }) {
  return (
    <span className="inline-flex gap-1 items-center py-1" aria-label="Đang trả lời">
      {[0, 150, 300].map((d) => (
        <span key={d} className="inline-block w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: color, animationDelay: `${d}ms` }} />
      ))}
    </span>
  );
}
