"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { BRAND_NAME } from "@/lib/brand";
import AssistantChat from "@/components/chat/AssistantChat";
import {
  customerTransport, staffTransport, fetchEmbedConfig, assetUrl, type EmbedConfig,
} from "@/lib/chat/transport";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const PROTOCOL = "msbka/1";
const STAFF_TOKEN_KEY = "querion-embed-staff-token";
const STAFF_REFRESH_KEY = "querion-embed-staff-refresh";
const STAFF_NAME_KEY = "querion-embed-staff-name";

type Phase =
  | { kind: "loading" }
  | { kind: "blocked"; reason: string }
  | { kind: "ready"; cfg: EmbedConfig; parentOrigin: string | null };

/** Read #k=…&o=…&preview=1 from the fragment (never sent to the server). */
function readFragment() {
  const h = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return { key: h.get("k") || "", origin: h.get("o") || "", preview: h.get("preview") === "1" };
}

/** Origin of the page that embeds us, as far as the browser lets us know. */
function detectParentOrigin(): string | null {
  if (window.self === window.top) return null;
  const anc = (window.location as any).ancestorOrigins as DOMStringList | undefined;
  if (anc && anc.length > 0) return anc[0];
  try { if (document.referrer) return new URL(document.referrer).origin; } catch { /* ignore */ }
  return null;
}

export default function EmbedPage() {
  const params = useParams();
  const appId = params.appId as string;
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [apiKey, setApiKey] = useState("");
  const [visible, setVisible] = useState(true);
  const visibleRef = useRef(true);
  const parentRef = useRef<string | null>(null);

  const post = useCallback((msg: Record<string, unknown>) => {
    if (window.self === window.top) return;
    const target = parentRef.current;
    if (!target) return; // never broadcast with "*"
    window.parent.postMessage({ protocol: PROTOCOL, ...msg }, target);
  }, []);

  // ---- boot: verify parent origin, load config ----
  useEffect(() => {
    (async () => {
      const frag = readFragment();
      setApiKey(frag.key);
      if (!frag.key) { setPhase({ kind: "blocked", reason: "Thiếu mã truy cập trợ lý." }); return; }

      const framed = window.self !== window.top;
      const detected = detectParentOrigin();
      const claimed = frag.origin || null;
      const parentOrigin = detected || claimed;
      if (framed && detected && claimed && detected !== claimed) {
        setPhase({ kind: "blocked", reason: "Origin của trang nhúng không khớp." }); return;
      }

      const cfg = await fetchEmbedConfig(appId, frag.key);
      if (!cfg) { setPhase({ kind: "blocked", reason: "Trợ lý không tồn tại, chưa công bố hoặc mã truy cập sai." }); return; }

      if (framed) {
        const selfOrigin = window.location.origin;
        const allowed = parentOrigin === selfOrigin /* admin preview */ || (cfg.embed_enabled && !!parentOrigin && cfg.allowed_origins.includes(parentOrigin));
        if (!allowed) {
          setPhase({ kind: "blocked", reason: cfg.embed_enabled ? `Trang ${parentOrigin || "này"} không được phép nhúng trợ lý.` : "Trợ lý chưa bật tính năng nhúng." });
          return;
        }
        parentRef.current = parentOrigin;
      }
      setPhase({ kind: "ready", cfg, parentOrigin: framed ? parentOrigin : null });
    })();
  }, [appId]);

  // ---- handshake + messages from the host page ----
  useEffect(() => {
    if (phase.kind !== "ready") return;
    const onMsg = (e: MessageEvent) => {
      if (!parentRef.current || e.origin !== parentRef.current) return;
      const d = e.data;
      if (!d || d.protocol !== PROTOCOL || typeof d.type !== "string") return;
      if (d.type === "visibility") { visibleRef.current = !!d.visible; setVisible(!!d.visible); }
    };
    window.addEventListener("message", onMsg);
    // logo_url is API-relative; the host page needs an absolute URL for the launcher image
    post({ type: "ready", widget: { ...phase.cfg.widget, logo_url: assetUrl(phase.cfg.logo_url) }, audience: phase.cfg.audience });
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") post({ type: "close" }); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("message", onMsg); window.removeEventListener("keydown", onKey); };
  }, [phase, post]);

  const onAnswer = useCallback(() => { if (!visibleRef.current) post({ type: "unread", count: 1 }); }, [post]);
  const onClose = useCallback(() => post({ type: "close" }), [post]);

  if (phase.kind === "loading") return <div style={{ height: "100%", background: "#f7f7f9" }} />;
  if (phase.kind === "blocked") return <Blocked reason={phase.reason} />;

  const { cfg, parentOrigin } = phase;
  const embedOrigin = parentOrigin && parentOrigin !== window.location.origin ? parentOrigin : null;
  const storageSuffix = `${appId}-${parentOrigin || "self"}`;

  if (cfg.audience === "staff") {
    return <StaffEmbed appId={appId} cfg={cfg} embedOrigin={embedOrigin} storageSuffix={storageSuffix} onAnswer={onAnswer} onClose={onClose} visible={visible} />;
  }
  return (
    <AssistantChat
      transport={customerTransport(appId, apiKey, embedOrigin)}
      widget={cfg.widget} logoUrl={assetUrl(cfg.logo_url)} variant="embed" brandName={BRAND_NAME}
      storageKey={`querion-embed-conv-${storageSuffix}`}
      onAnswer={onAnswer} onClose={onClose}
    />
  );
}

/* ------------------------------------------------------------------ */
/* Staff assistant inside the widget: login form → chat with JWT       */
/* ------------------------------------------------------------------ */

function StaffEmbed({ appId, cfg, embedOrigin, storageSuffix, onAnswer, onClose }: {
  appId: string; cfg: EmbedConfig; embedOrigin: string | null; storageSuffix: string;
  onAnswer: () => void; onClose: () => void; visible: boolean;
}) {
  const [token, setToken] = useState<string | null>(null);
  const [name, setName] = useState<string>("");
  const [checked, setChecked] = useState(false);

  // restore session (storage is partitioned per embedding site; may be blocked)
  useEffect(() => {
    (async () => {
      let t: string | null = null, rt: string | null = null, n = "";
      try { t = localStorage.getItem(STAFF_TOKEN_KEY); rt = localStorage.getItem(STAFF_REFRESH_KEY); n = localStorage.getItem(STAFF_NAME_KEY) || ""; } catch { /* blocked */ }
      if (t) {
        const me = await fetch(`${API_BASE}/v1/staff/me`, { headers: { Authorization: `Bearer ${t}` } });
        if (me.ok) { const j = await me.json(); setToken(t); setName(j.name || n); setChecked(true); return; }
      }
      if (rt) {
        const r = await fetch(`${API_BASE}/v1/staff/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: rt }) });
        if (r.ok) { const j = await r.json(); try { localStorage.setItem(STAFF_TOKEN_KEY, j.access_token); } catch { /* ignore */ } setToken(j.access_token); setName(n); setChecked(true); return; }
      }
      setChecked(true);
    })();
  }, []);

  const logout = () => {
    setToken(null); setName("");
    try { localStorage.removeItem(STAFF_TOKEN_KEY); localStorage.removeItem(STAFF_REFRESH_KEY); localStorage.removeItem(STAFF_NAME_KEY); } catch { /* ignore */ }
  };

  const tokenRef = useRef<string | null>(null);
  tokenRef.current = token;
  const transport = useMemo(() => staffTransport(appId, () => tokenRef.current, embedOrigin), [appId, embedOrigin]);

  if (!checked) return <div style={{ height: "100%", background: "#f7f7f9" }} />;
  if (!token) {
    return <StaffLogin widget={cfg.widget} logoUrl={assetUrl(cfg.logo_url)} onClose={onClose} onLoggedIn={(t, rt, n) => {
      try { localStorage.setItem(STAFF_TOKEN_KEY, t); localStorage.setItem(STAFF_REFRESH_KEY, rt); localStorage.setItem(STAFF_NAME_KEY, n); } catch { /* ignore */ }
      setToken(t); setName(n);
    }} />;
  }
  return (
    <AssistantChat
      transport={transport} widget={cfg.widget} logoUrl={assetUrl(cfg.logo_url)} variant="embed" brandName={BRAND_NAME}
      storageKey={`querion-embed-staff-conv-${storageSuffix}`}
      onAnswer={onAnswer} onClose={onClose} askReasonOnDown
      headerExtra={
        <button onClick={logout} title={`Đăng xuất (${name})`} aria-label="Đăng xuất" className="rounded-lg px-2 py-1 text-[11px] font-medium truncate"
          style={{ background: "rgba(255,255,255,0.18)", color: "#fff", maxWidth: 120 }}>
          {name || "Đăng xuất"} ⏏
        </button>
      }
    />
  );
}

function StaffLogin({ widget, logoUrl, onLoggedIn, onClose }: {
  widget: EmbedConfig["widget"]; logoUrl?: string | null; onLoggedIn: (token: string, refresh: string, name: string) => void; onClose: () => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const primary = widget.primary_color || "#1f3a5f";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const r = await fetch(`${API_BASE}/v1/staff/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(j.detail || "Đăng nhập thất bại"); }
      const j = await r.json();
      if (j.employee?.must_change_password) {
        setErr("Tài khoản cần đổi mật khẩu lần đầu. Mở cổng cán bộ để đổi rồi quay lại.");
        window.open("/staff/login", "_blank", "noopener");
        return;
      }
      onLoggedIn(j.access_token, j.refresh_token, j.employee?.name || email);
    } catch (e: any) { setErr(e.message || "Đăng nhập thất bại"); }
    finally { setBusy(false); }
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: "#f7f7f9", color: "#0f172a" }}>
      <header className="flex items-center justify-between px-4 py-3" style={{ background: primary, color: "#fff" }}>
        <div className="flex items-center gap-3 min-w-0">
          {logoUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logoUrl} alt="" aria-hidden="true" className="rounded-full shrink-0" style={{ width: 34, height: 34, objectFit: "cover", background: "rgba(255,255,255,0.92)" }} />
          )}
          <div className="min-w-0">
            <h1 className="text-sm font-semibold truncate">{widget.title}</h1>
            <p className="text-xs truncate" style={{ opacity: 0.85 }}>Dành cho cán bộ — đăng nhập để hỏi</p>
          </div>
        </div>
        <button onClick={onClose} aria-label="Thu nhỏ" className="rounded-lg p-1.5" style={{ background: "rgba(255,255,255,0.18)" }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/></svg>
        </button>
      </header>
      <form onSubmit={submit} className="flex-1 flex flex-col justify-center gap-3 px-6">
        <p className="text-sm">{widget.greeting || "Đăng nhập bằng tài khoản cán bộ để sử dụng trợ lý."}</p>
        {err && <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#b91c1c" }}>{err}</div>}
        <input type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email cán bộ" aria-label="Email"
          className="text-sm rounded-lg px-3 py-2.5 outline-none" style={{ background: "#fff", border: "1px solid rgba(15,23,42,0.12)" }} />
        <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Mật khẩu" aria-label="Mật khẩu"
          className="text-sm rounded-lg px-3 py-2.5 outline-none" style={{ background: "#fff", border: "1px solid rgba(15,23,42,0.12)" }} />
        <button type="submit" disabled={busy} className="rounded-lg py-2.5 text-sm font-semibold" style={{ background: primary, color: "#fff" }}>
          {busy ? "…" : "Đăng nhập"}
        </button>
        <p className="text-[10px] text-center" style={{ color: "#64748b" }}>Phiên đăng nhập chỉ lưu trong khung chat này. Không nhập thông tin khách hàng vào trợ lý.</p>
      </form>
    </div>
  );
}

function Blocked({ reason }: { reason: string }) {
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#f7f7f9", color: "#0f172a", padding: 24 }}>
      <div className="rounded-xl p-5 text-center text-sm" style={{ background: "#fff", border: "1px solid rgba(15,23,42,0.08)", maxWidth: 320 }}>
        <p className="font-semibold mb-1">Không thể mở trợ lý</p>
        <p style={{ color: "#64748b" }}>{reason}</p>
      </div>
    </div>
  );
}
