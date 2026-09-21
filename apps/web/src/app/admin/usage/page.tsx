"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { getAuditFilters, AuditFilters } from "@/lib/api/audit";
import {
  getUsageSummary, UsageBucket, UsageQuery, UsageSummary, COMPONENTS, CHANNEL_LABEL,
} from "@/lib/api/usage";

const fieldStyle = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };
const PERIODS = [{ v: 1, l: "Hôm nay" }, { v: 7, l: "7 ngày" }, { v: 30, l: "30 ngày" }, { v: 90, l: "90 ngày" }];
const COMPONENT_BY_KEY = Object.fromEntries(COMPONENTS.map((c) => [c.key, c]));

const fmt = (n: number) => n.toLocaleString("vi-VN");
const compact = (n: number) => new Intl.NumberFormat("vi-VN", { notation: "compact", maximumFractionDigits: 1 }).format(n);

export default function UsagePage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<AuditFilters | null>(null);
  const [query, setQuery] = useState<UsageQuery>({ days: 30 });
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setData(await getUsageSummary(query)); }
    catch (e: any) { setError(e.message || "Không tải được số liệu token"); }
    finally { setLoading(false); }
  }, [query]);

  useEffect(() => { getAuditFilters().then(setFilters).catch(() => setFilters(null)); }, []);
  useEffect(() => { load(); }, [load]);

  const set = (patch: Partial<UsageQuery>) => setQuery((q) => ({ ...q, ...patch }));
  const appsForWs = filters?.apps.filter((a) => !query.workspace_id || a.workspace_id === query.workspace_id) || [];

  if (!isAdmin) return <div className="text-center py-20 text-sm" style={{ color: "var(--muted)" }}>Không có quyền truy cập</div>;

  const t = data?.totals;
  const llm = data?.by_purpose.find((b) => b.key === "llm")?.total_tokens || 0;
  const emb = data?.by_purpose.find((b) => b.key === "embedding")?.total_tokens || 0;

  return (
    <div>
      <div className="page-header flex items-center justify-between mb-5">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Token sử dụng</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            Lượng token mô hình AI đã dùng theo thành phần, kênh, trợ lý, đơn vị và mô hình. Số liệu lấy từ báo cáo của nhà cung cấp; lượt nào nhà cung cấp không báo thì được ước tính theo độ dài văn bản.
          </p>
        </div>
        <button onClick={load} className="shrink-0 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-medium" style={{ background: "var(--card)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
          ↻ Tải lại
        </button>
      </div>

      {/* Filters */}
      <div className="grid gap-2 mb-5 md:grid-cols-5">
        <div className="flex rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }} data-testid="usage-period">
          {PERIODS.map((p) => (
            <button key={p.v} onClick={() => set({ days: p.v })} className="flex-1 text-xs py-2 font-medium"
              style={{ background: query.days === p.v ? "var(--accent)" : "var(--background)", color: query.days === p.v ? "#fff" : "var(--foreground)" }}>
              {p.l}
            </button>
          ))}
        </div>
        <select value={query.workspace_id || ""} onChange={(e) => set({ workspace_id: e.target.value || undefined, app_id: undefined })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Tất cả đơn vị</option>
          {filters?.workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
        <select value={query.app_id || ""} onChange={(e) => set({ app_id: e.target.value || undefined })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Tất cả trợ lý</option>
          {appsForWs.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={query.channel || ""} onChange={(e) => set({ channel: e.target.value || undefined })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Mọi kênh</option>
          {Object.entries(CHANNEL_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select value={query.component || ""} onChange={(e) => set({ component: e.target.value || undefined })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Mọi thành phần</option>
          {COMPONENTS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
      </div>

      {error && <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>{error}</div>}

      {loading && !data ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : data && t ? (
        <div style={{ opacity: loading ? 0.6 : 1 }}>
          <div className="grid gap-3 mb-5 grid-cols-2 md:grid-cols-3 lg:grid-cols-6" data-testid="usage-tiles">
            <Tile label="Tổng token" value={compact(t.total_tokens)} hint={`${fmt(t.total_tokens)} token`} />
            <Tile label="Đầu vào (prompt)" value={compact(t.prompt_tokens)} hint={pct(t.prompt_tokens, t.total_tokens)} />
            <Tile label="Đầu ra (completion)" value={compact(t.completion_tokens)} hint={pct(t.completion_tokens, t.total_tokens)} />
            <Tile label="Lượt gọi mô hình" value={fmt(t.calls)} hint={t.calls ? `~${compact(Math.round(t.total_tokens / t.calls))} token/lượt` : undefined} />
            <Tile label="LLM / Embedding" value={`${pct(llm, t.total_tokens, true)} / ${pct(emb, t.total_tokens, true)}`} hint={`${compact(llm)} / ${compact(emb)}`} />
            <Tile label="Ước tính" value={pct(t.estimated_calls, t.calls, true)} hint={t.estimated_calls ? `${fmt(t.estimated_calls)} lượt không có số liệu từ nhà cung cấp` : "Mọi lượt có số liệu chính xác"}
              tone={t.calls && t.estimated_calls / t.calls > 0.2 ? "warn" : undefined} />
          </div>

          <DailyChart data={data} />

          <div className="grid gap-4 lg:grid-cols-2 mt-5">
            <Breakdown title="Theo thành phần" total={t.total_tokens} testId="usage-by-component"
              rows={data.by_component.map((b) => ({ b, label: COMPONENT_BY_KEY[b.key || ""]?.label || b.key || "—", hint: COMPONENT_BY_KEY[b.key || ""]?.hint, color: COMPONENT_BY_KEY[b.key || ""]?.color }))} />
            <Breakdown title="Theo kênh" total={t.total_tokens} testId="usage-by-channel"
              rows={data.by_channel.map((b) => ({ b, label: CHANNEL_LABEL[b.key || ""] || b.key || "Khác" }))} />
            <Breakdown title="Theo trợ lý" total={t.total_tokens} testId="usage-by-app"
              rows={data.by_app.map((b) => ({ b, label: b.label || "Không gắn trợ lý", hint: b.key ? undefined : "Lập chỉ mục, thử tra cứu, sửa đoạn văn bản" }))} />
            <Breakdown title="Theo đơn vị" total={t.total_tokens} testId="usage-by-workspace"
              rows={data.by_workspace.map((b) => ({ b, label: b.label || "Không xác định" }))} />
            <Breakdown title="Theo mô hình" total={t.total_tokens} testId="usage-by-model"
              rows={data.by_model.map((b) => ({ b, label: b.key || "—", hint: b.label === "embedding" ? "Embedding" : "LLM" }))} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function pct(part: number, whole: number, bare = false) {
  if (!whole) return bare ? "0%" : "—";
  const v = (part / whole) * 100;
  const s = `${v < 10 && v > 0 ? v.toFixed(1) : Math.round(v)}%`;
  return bare ? s : `${s} tổng`;
}

function DailyChart({ data }: { data: UsageSummary }) {
  const max = Math.max(1, ...data.by_day.map((d) => d.total_tokens));
  const present = useMemo(() => COMPONENTS.filter((c) => data.by_day.some((d) => d.by_component[c.key])), [data]);
  const labelEvery = data.by_day.length > 31 ? 7 : data.by_day.length > 10 ? 3 : 1;
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--card)", border: "1px solid var(--border)" }} data-testid="usage-daily">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Token theo ngày</p>
        <div className="flex flex-wrap gap-3">
          {present.map((c) => (
            <span key={c.key} className="flex items-center gap-1 text-[11px]" style={{ color: "var(--muted)" }}>
              <span className="rounded-sm" style={{ width: 10, height: 10, background: c.color }} />{c.label}
            </span>
          ))}
        </div>
      </div>
      <div className="flex items-end gap-[3px]" style={{ height: 180 }}>
        {data.by_day.map((d) => (
          <div key={d.day} className="flex-1 flex flex-col-reverse rounded-t-sm overflow-hidden" style={{ height: `${(d.total_tokens / max) * 100}%`, minHeight: d.total_tokens ? 2 : 0 }}
            title={`${fmtDay(d.day)}: ${fmt(d.total_tokens)} token\n` + COMPONENTS.filter((c) => d.by_component[c.key]).map((c) => `${c.label}: ${fmt(d.by_component[c.key])}`).join("\n")}>
            {COMPONENTS.filter((c) => d.by_component[c.key]).map((c) => (
              <div key={c.key} style={{ height: `${(d.by_component[c.key] / d.total_tokens) * 100}%`, background: c.color }} />
            ))}
          </div>
        ))}
      </div>
      <div className="flex gap-[3px] mt-1">
        {data.by_day.map((d, i) => (
          <div key={d.day} className="flex-1 text-center text-[9px] truncate" style={{ color: "var(--muted)" }}>
            {i % labelEvery === 0 || i === data.by_day.length - 1 ? fmtDay(d.day) : ""}
          </div>
        ))}
      </div>
    </div>
  );
}

function fmtDay(iso: string) {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

function Breakdown({ title, rows, total, testId }: {
  title: string; total: number; testId?: string;
  rows: { b: UsageBucket; label: string; hint?: string; color?: string }[];
}) {
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--card)", border: "1px solid var(--border)" }} data-testid={testId}>
      <p className="text-[10px] font-bold uppercase tracking-wider mb-3" style={{ color: "var(--muted)" }}>{title}</p>
      {rows.length === 0 ? <p className="text-xs" style={{ color: "var(--muted)" }}>Chưa có số liệu.</p> : (
        <div className="space-y-3">
          {rows.map(({ b, label, hint, color }) => (
            <div key={`${b.key}-${label}`}>
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="min-w-0 truncate font-medium" style={{ color: "var(--foreground)" }} title={hint || label}>
                  {label}{b.estimated_calls > 0 && <span title={`${b.estimated_calls} lượt ước tính`} style={{ color: "#f59e0b" }}> ~</span>}
                </span>
                <span className="shrink-0 font-mono" style={{ color: "var(--foreground)" }}>{fmt(b.total_tokens)}</span>
              </div>
              <div className="mt-1 rounded-full overflow-hidden" style={{ height: 6, background: "var(--background)" }}>
                <div style={{ width: `${total ? Math.max(1, (b.total_tokens / total) * 100) : 0}%`, height: "100%", background: color || "var(--accent)" }} />
              </div>
              <div className="flex justify-between text-[10px] mt-0.5" style={{ color: "var(--muted)" }}>
                <span className="truncate">{hint || `${pct(b.total_tokens, total)}`}</span>
                <span className="shrink-0">vào {compact(b.prompt_tokens)} · ra {compact(b.completion_tokens)} · {fmt(b.calls)} lượt</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, hint, tone }: { label: string; value: string | number; hint?: string; tone?: "warn" }) {
  return (
    <div className="rounded-xl px-4 py-3" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
      <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>{label}</p>
      <p className="text-xl font-semibold mt-0.5" style={{ color: tone === "warn" ? "#f59e0b" : "var(--foreground)" }}>{value}</p>
      {hint && <p className="text-[10px] truncate" style={{ color: "var(--muted)" }} title={hint}>{hint}</p>}
    </div>
  );
}
