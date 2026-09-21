/**
 * The panel: login → pick an assistant → chat. Runs as a chrome-extension:// page inside the
 * iframe the content script draws, so it can call the staff API directly (host_permissions) and
 * keep the session in chrome.storage, shared by every page the bubble appears on.
 *
 * The chat UI is the web app's own `AssistantChat`, so citations, tool chips, approval cards and
 * download buttons behave exactly as in the staff portal.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AssistantChat from "@/components/chat/AssistantChat";
import { assetUrl, configureTransport, staffTransport, type WidgetConfig } from "@/lib/chat/transport";
import { ApiError, ensureFreshToken, listApps, login, logout, type AppGroup, type StaffApp } from "../lib/api";
import { PROTOCOL, type PageContext, type ToPage, type ToPanel } from "../lib/bridge";
import { anyHostMatches } from "../lib/hosts";
import { getLastAppId, getSession, loadConfig, setLastAppId, type Config, type Session } from "../lib/storage";

type View = "loading" | "login" | "pick" | "chat" | "error";

/** Origin of the page the bubble sits on — from the browser, not from the page. */
function pageOrigin(): string | null {
  const anc = (window.location as unknown as { ancestorOrigins?: DOMStringList }).ancestorOrigins;
  if (anc && anc.length > 0) return anc[0];
  const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return h.get("o");
}

export default function App() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [groups, setGroups] = useState<AppGroup[]>([]);
  const [current, setCurrent] = useState<StaffApp | null>(null);
  const [view, setView] = useState<View>("loading");
  const [error, setError] = useState<string | null>(null);
  const [context, setContext] = useState<PageContext | null>(null);
  const [prefill, setPrefill] = useState<string | null>(null);
  const [selectionDismissed, setSelectionDismissed] = useState("");
  const [contextReady, setContextReady] = useState(false);
  const visibleRef = useRef(true);
  const parent = useMemo(pageOrigin, []);
  // framed = inside the bubble's iframe on a web page; otherwise we are the Side Panel (browser-level,
  // no host page of our own) and learn about the active tab through chrome.tabs instead
  const framed = window.self !== window.top && !!parent;
  const sidePanel = !framed;

  const post = useCallback((msg: ToPage) => {
    if (!framed || !parent) return;
    window.parent.postMessage({ protocol: PROTOCOL, ...msg }, parent);
  }, [framed, parent]);

  // ---- messages from the bubble (page context, visibility) ----
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (!framed || e.source !== window.parent || e.origin !== parent) return;
      const d = e.data as (ToPanel & { protocol?: string }) | undefined;
      if (!d || d.protocol !== PROTOCOL) return;
      if (d.type === "context") setContext(d.context);
      else if (d.type === "visibility") visibleRef.current = d.visible;
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [framed, parent]);

  // ---- side panel: tell the background we are open (bubbles hide) until this page goes away ----
  useEffect(() => {
    if (!sidePanel || typeof chrome === "undefined" || !chrome.runtime?.connect) return;
    let port: chrome.runtime.Port | null = null;
    try { port = chrome.runtime.connect({ name: "msbka-sidepanel" }); } catch { /* not an extension context */ }
    return () => { try { port?.disconnect(); } catch { /* already gone */ } };
  }, [sidePanel]);

  // ---- side panel: follow the active tab (host for the default assistant, selection for the chip) ----
  useEffect(() => {
    if (!sidePanel || typeof chrome === "undefined" || !chrome.tabs) return;
    const fromTab = async (tab: chrome.tabs.Tab | undefined) => {
      if (!tab?.url || !/^https?:/.test(tab.url)) { setContext(null); return; }
      const u = new URL(tab.url);
      let ctx: PageContext = { origin: u.origin, host: u.host, href: tab.url, title: tab.title || "", selection: "" };
      try {
        if (tab.id !== undefined) {
          const fresh = await chrome.tabs.sendMessage(tab.id, { type: "get-context" }) as PageContext | undefined;
          if (fresh?.host) ctx = fresh;
        }
      } catch { /* no content script on that page */ }
      setContext(ctx);
    };
    const refresh = async () => {
      try {
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        await fromTab(tab);
      } finally { setContextReady(true); }
    };
    void refresh();
    const onActivated = () => { void refresh(); };
    const onUpdated = (_id: number, info: { url?: string; status?: string }, tab: chrome.tabs.Tab) => { if (tab.active && (info.url || info.status === "complete")) void fromTab(tab); };
    const onMessage = (msg: { type?: string; context?: PageContext }, sender: chrome.runtime.MessageSender) => {
      if (msg?.type === "selection" && msg.context && sender.tab?.active) setContext(msg.context);
    };
    chrome.tabs.onActivated.addListener(onActivated);
    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.runtime.onMessage.addListener(onMessage);
    return () => {
      chrome.tabs.onActivated.removeListener(onActivated);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      chrome.runtime.onMessage.removeListener(onMessage);
    };
  }, [sidePanel]);

  const allApps = useMemo(() => groups.flatMap((g) => g.apps), [groups]);

  // ---- boot: config → session → assistants ----
  const loadAssistants = useCallback(async (c: Config, s: Session) => {
    const list = await listApps(c.apiBase, s.access);
    setGroups(list);
    return list.flatMap((g) => g.apps);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const c = await loadConfig();
        configureTransport({ apiBase: c.apiBase });
        setCfg(c);
        const s = await ensureFreshToken(c.apiBase);
        if (!s) { setView("login"); return; }
        setSession(s);
        const apps = await loadAssistants(c, s);
        if (apps.length === 0) { setError("Chưa có trợ lý nào được mở cho browser extension. Liên hệ quản trị viên."); setView("error"); return; }
        setView("pick"); // the effect below promotes to chat once a default is known
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) { await logout(); setView("login"); return; }
        setError(e instanceof Error ? e.message : "Không kết nối được máy chủ"); setView("error");
      }
    })();
  }, [loadAssistants]);

  // keep the token fresh while the panel lives
  useEffect(() => {
    if (!cfg || !session) return;
    const t = window.setInterval(async () => {
      const s = await ensureFreshToken(cfg.apiBase);
      if (!s) { setSession(null); setView("login"); } else setSession(s);
    }, 5 * 60_000);
    return () => window.clearInterval(t);
  }, [cfg, session]);

  // ---- default assistant: page rule → last used → the only one ----
  const decided = useRef(false);
  useEffect(() => {
    if (decided.current || view !== "pick" || allApps.length === 0) return;
    if (sidePanel && typeof chrome !== "undefined" && chrome.tabs && !contextReady) return;
    (async () => {
      const host = context?.host || (parent ? new URL(parent).host : "");
      const byHost = host ? allApps.find((a) => anyHostMatches(a.extension_hosts, host)) : undefined;
      const last = await getLastAppId();
      const byLast = last ? allApps.find((a) => a.id === last) : undefined;
      const pick = byHost || byLast || (allApps.length === 1 ? allApps[0] : undefined);
      decided.current = true;
      if (pick) choose(pick);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, allApps, context?.host, contextReady]);

  const choose = (app: StaffApp) => {
    setCurrent(app); setView("chat"); void setLastAppId(app.id);
    post({ type: "ready", color: app.primary_color || "#ee6d1f", title: app.name });
  };

  const onLogin = async (email: string, password: string) => {
    if (!cfg) return;
    setError(null);
    try {
      const s = await login(cfg.apiBase, email, password);
      setSession(s);
      const apps = await loadAssistants(cfg, s);
      if (apps.length === 0) { setError("Chưa có trợ lý nào được mở cho browser extension."); setView("error"); return; }
      decided.current = false;
      setView("pick");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không kết nối được máy chủ");
    }
  };

  const onLogout = async () => { await logout(); setSession(null); setCurrent(null); setGroups([]); decided.current = false; setView("login"); };

  const getToken = useCallback(() => session?.access || null, [session]);
  const pageOriginForAudit = parent || context?.origin || null;
  const transport = useMemo(
    () => (current ? staffTransport(current.id, getToken, null, pageOriginForAudit ? { "X-Page-Origin": pageOriginForAudit } : undefined) : null),
    [current, getToken, pageOriginForAudit],
  );
  const widget: WidgetConfig | null = useMemo(() => current ? {
    title: current.name, subtitle: current.description || undefined, greeting: current.greeting,
    primary_color: current.primary_color || "#ee6d1f", position: "right", suggestions: current.suggestions || [],
    show_powered_by: false, theme: "auto",
  } : null, [current]);

  const selection = context?.selection && context.selection !== selectionDismissed ? context.selection : "";

  if (view === "loading") return <Center>…</Center>;
  if (view === "error") return <Center><p style={{ color: "#b91c1c", fontSize: 13, padding: 16, textAlign: "center" }}>{error}</p></Center>;
  if (view === "login") return <Login brand={cfg?.brandName || "MSB Knowledge Assistant"} webBase={cfg?.webBase || ""} error={error} onSubmit={onLogin} />;

  if (view === "pick" || !current || !transport || !widget) {
    return (
      <Picker groups={groups} host={context?.host || (parent ? new URL(parent).host : "")} current={current}
        employee={session?.employee} onPick={choose} onLogout={onLogout} onBack={current ? () => setView("chat") : undefined} />
    );
  }

  return (
    <div style={{ position: "relative", height: "100%" }}>
      <AssistantChat
        key={current.id}
        transport={transport}
        widget={widget}
        variant="embed"
        storageKey={`msbka-ext-conv-${current.id}`}
        brandName={cfg?.brandName || "MSB Knowledge Assistant"}
        logoUrl={assetUrl(current.logo_url)}
        askReasonOnDown
        prefill={prefill}
        onClose={framed ? () => post({ type: "close" }) : undefined}
        onAnswer={() => { if (!visibleRef.current) post({ type: "unread", count: 1 }); }}
        headerExtra={
          <>
            <button onClick={() => setView("pick")} title="Đổi trợ lý" aria-label="Đổi trợ lý" data-testid="switch-assistant"
              className="rounded-lg p-1.5 text-xs font-medium" style={{ background: "rgba(255,255,255,0.18)", color: "#fff" }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.5"/></svg>
            </button>
            <button onClick={onLogout} title="Đăng xuất" aria-label="Đăng xuất" data-testid="ext-logout"
              className="rounded-lg p-1.5 text-xs font-medium" style={{ background: "rgba(255,255,255,0.18)", color: "#fff" }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 3H3.5A1.5 1.5 0 0 0 2 4.5v7A1.5 1.5 0 0 0 3.5 13H6M10 11l3-3-3-3M13 8H6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </>
        }
      />
      {selection && (
        <div data-testid="selection-chip" className="rounded-xl px-3 py-2 text-xs shadow-lg flex items-start gap-2"
          style={{ position: "absolute", left: 12, right: 12, bottom: 84, background: "#0f172a", color: "#fff" }}>
          <span className="min-w-0 flex-1">
            <span style={{ color: "#94a3b8" }}>Đang bôi đen trên trang: </span>
            <span className="italic">“{selection.length > 90 ? selection.slice(0, 90) + "…" : selection}”</span>
          </span>
          <button onClick={() => { setPrefill(`Về đoạn sau trên trang "${context?.title || ""}":\n"${selection}"\n\n`); setSelectionDismissed(selection); }}
            className="rounded-md px-2 py-1 font-semibold shrink-0" style={{ background: widget.primary_color, color: "#fff" }} data-testid="ask-selection">
            Hỏi về đoạn này
          </button>
          <button onClick={() => setSelectionDismissed(selection)} aria-label="Bỏ qua" className="shrink-0" style={{ color: "#94a3b8" }}>×</button>
        </div>
      )}
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>{children}</div>;
}

function Login({ brand, webBase, error, onSubmit }: { brand: string; webBase: string; error: string | null; onSubmit: (e: string, p: string) => Promise<void> }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => { e.preventDefault(); setBusy(true); try { await onSubmit(email.trim(), password); } finally { setBusy(false); } };
  const field = { width: "100%", boxSizing: "border-box" as const, padding: "9px 12px", borderRadius: 10, border: "1px solid #cbd5e1", fontSize: 14, background: "#fff" };
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", padding: 24, color: "#0f172a" }}>
      <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#ee6d1f", margin: 0 }}>{brand}</p>
      <h1 style={{ fontSize: 18, fontWeight: 600, margin: "4px 0 4px" }}>Đăng nhập cán bộ</h1>
      <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 16px" }}>Một lần cho mọi trang trên trình duyệt này. Không nhập mật khẩu khách hàng hay mã OTP vào khung chat.</p>
      <form onSubmit={submit} style={{ display: "grid", gap: 10 }}>
        <input type="email" required autoComplete="username" placeholder="email@msb.com.vn" value={email} onChange={(e) => setEmail(e.target.value)} style={field} />
        <input type="password" required autoComplete="current-password" placeholder="Mật khẩu" value={password} onChange={(e) => setPassword(e.target.value)} style={field} />
        {error && <p style={{ color: "#b91c1c", fontSize: 12, margin: 0 }}>{error}</p>}
        <button type="submit" disabled={busy} style={{ padding: "10px 12px", borderRadius: 10, border: 0, background: "#ee6d1f", color: "#fff", fontWeight: 600, cursor: "pointer", opacity: busy ? 0.7 : 1 }}>
          {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </button>
      </form>
      {webBase && <p style={{ fontSize: 11, color: "#64748b", marginTop: 14 }}>Lần đầu đăng nhập cần đổi mật khẩu? Vào <a href={`${webBase}/staff/login`} target="_blank" rel="noreferrer" style={{ color: "#ee6d1f" }}>cổng cán bộ</a> rồi quay lại.</p>}
    </div>
  );
}

function Picker({ groups, host, current, employee, onPick, onLogout, onBack }: {
  groups: AppGroup[]; host: string; current: StaffApp | null; employee?: Session["employee"];
  onPick: (a: StaffApp) => void; onLogout: () => void; onBack?: () => void;
}) {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", color: "#0f172a" }} data-testid="assistant-picker">
      <div style={{ padding: "14px 16px 10px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 8 }}>
        {onBack && <button onClick={onBack} aria-label="Quay lại" style={{ border: 0, background: "transparent", cursor: "pointer", fontSize: 16 }}>←</button>}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Chọn trợ lý</p>
          {employee && <p style={{ margin: 0, fontSize: 11, color: "#64748b" }}>{employee.name}{employee.workspace_name ? ` · ${employee.workspace_name}` : ""}</p>}
        </div>
        <button onClick={onLogout} style={{ border: "1px solid #cbd5e1", background: "#fff", borderRadius: 8, padding: "4px 10px", fontSize: 11, cursor: "pointer" }}>Đăng xuất</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {groups.map((g) => (
          <div key={g.workspace_name} style={{ marginBottom: 14 }}>
            <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", color: "#64748b", margin: "0 4px 6px" }}>{g.workspace_name}</p>
            {g.apps.map((a) => {
              const isDefault = host && anyHostMatches(a.extension_hosts, host);
              const active = current?.id === a.id;
              return (
                <button key={a.id} onClick={() => onPick(a)} data-testid={`pick-${a.id}`}
                  style={{ display: "flex", gap: 10, width: "100%", textAlign: "left", padding: "10px 12px", marginBottom: 6, borderRadius: 12, cursor: "pointer",
                    background: active ? "rgba(238,109,31,0.10)" : "#fff", border: `1px solid ${active ? "#ee6d1f" : "#e2e8f0"}` }}>
                  {a.logo_url
                    ? <img src={assetUrl(a.logo_url) || undefined} alt="" style={{ width: 32, height: 32, borderRadius: 16, objectFit: "cover", flexShrink: 0 }} />
                    : <span style={{ width: 32, height: 32, borderRadius: 16, background: a.primary_color || "#ee6d1f", flexShrink: 0 }} />}
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{a.name}</span>
                      {a.share_scope === "bank" && <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 999, background: "rgba(59,130,246,0.12)", color: "#2563eb" }}>TOÀN NGÂN HÀNG</span>}
                      {isDefault && <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 999, background: "rgba(34,197,94,0.14)", color: "#15803d" }} data-testid="default-badge">MẶC ĐỊNH TRÊN TRANG NÀY</span>}
                    </span>
                    {a.description && <span style={{ display: "block", fontSize: 11, color: "#64748b", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.description}</span>}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
