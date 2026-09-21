"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  listAuditRuns, getAuditRun, getAuditSummary, getAuditFilters,
  AuditRunRow, AuditRunDetail, AuditSummary, AuditFilters, AuditQuery,
} from "@/lib/api/audit";
import { sourceLabel, sourceBody } from "@/lib/citations";
import Markdown from "@/components/ui/Markdown";
import { COMPONENTS } from "@/lib/api/usage";

const CHANNEL_LABEL: Record<string, string> = { staff: "Cán bộ", customer: "Khách hàng", admin_test: "Admin thử",
  embed: "Website nhúng", report: "Báo cáo", scheduled: "Theo lịch", form: "Biểu mẫu" };
const CHANNEL_STYLE: Record<string, { bg: string; color: string }> = {
  staff: { bg: "var(--accent-glow)", color: "var(--accent)" },
  customer: { bg: "rgba(34,197,94,0.12)", color: "#16a34a" },
  admin_test: { bg: "rgba(100,116,139,0.14)", color: "var(--muted)" },
  embed: { bg: "rgba(59,130,246,0.12)", color: "#2563eb" },
  report: { bg: "rgba(132,204,22,0.12)", color: "#84cc16" },
  scheduled: { bg: "rgba(14,165,233,0.12)", color: "#0ea5e9" },
  form: { bg: "rgba(168,85,247,0.12)", color: "#a855f7" },
};
const STATUS_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  completed: { bg: "rgba(34,197,94,0.12)", color: "#22c55e", label: "Thành công" },
  failed: { bg: "rgba(239,68,68,0.12)", color: "#ef4444", label: "Lỗi" },
  running: { bg: "rgba(245,158,11,0.12)", color: "#f59e0b", label: "Đang chạy" },
  blocked: { bg: "rgba(168,85,247,0.14)", color: "#7c3aed", label: "Bị chặn" },
  waiting: { bg: "rgba(59,130,246,0.12)", color: "#2563eb", label: "Chờ duyệt" },
  queued: { bg: "rgba(245,158,11,0.12)", color: "#f59e0b", label: "Đang chờ chạy" },
};
const NODE_LABEL: Record<string, string> = {
  retrieve: "Tra cứu kho tri thức", llm_generate: "Sinh câu trả lời (LLM)", parameter_extract: "Trích xuất / phân loại",
  if_else: "Rẽ nhánh", compose_prompt: "Soạn prompt", answer: "Trả lời", input: "Đầu vào", output: "Kết thúc",
  http_request: "Gọi API ngoài", code_execute: "Chạy mã", tool_call: "Gọi công cụ",
  render_document: "Xuất tài liệu",
};

const fieldStyle = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

export default function AuditPage() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<AuditFilters | null>(null);
  const [query, setQuery] = useState<AuditQuery>({ days: 30, limit: 100 });
  const [rows, setRows] = useState<AuditRunRow[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<AuditRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [r, s] = await Promise.all([
        listAuditRuns(query),
        getAuditSummary({ workspace_id: query.workspace_id, days: query.days }),
      ]);
      setRows(r);
      setSummary(s);
    } catch (e: any) {
      setError(e.message || "Không tải được nhật ký");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => { getAuditFilters().then(setFilters).catch(() => setFilters(null)); }, []);
  useEffect(() => { load(); }, [load]);

  const set = (patch: Partial<AuditQuery>) => setQuery((q) => ({ ...q, ...patch }));
  const appsForWs = filters?.apps.filter((a) => !query.workspace_id || a.workspace_id === query.workspace_id) || [];

  const openDetail = async (id: string) => {
    try { setDetail(await getAuditRun(id)); } catch { /* silent */ }
  };

  if (!isAdmin) return <div className="text-center py-20 text-sm" style={{ color: "var(--muted)" }}>Không có quyền truy cập</div>;

  return (
    <div>
      <div className="page-header flex items-center justify-between mb-5">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Nhật ký truy vấn</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            Ai hỏi gì, trợ lý trả lời dựa trên văn bản nào, độ trễ và đánh giá của người dùng — phục vụ kiểm soát tuân thủ.
          </p>
        </div>
        <button onClick={load} className="rounded-xl px-4 py-2 text-sm font-medium" style={{ background: "var(--card)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
          ↻ Tải lại
        </button>
      </div>

      {/* Summary tiles */}
      {summary && (
        <div className="grid gap-3 mb-5 grid-cols-2 md:grid-cols-4 lg:grid-cols-6">
          <Tile label="Lượt hỏi" value={summary.total_runs} hint={`${query.days} ngày`} />
          <Tile label="Cán bộ" value={summary.runs_by_channel.staff || 0} />
          <Tile label="Khách hàng" value={summary.runs_by_channel.customer || 0} />
          <Tile label="Độ trễ TB" value={summary.avg_latency_ms != null ? `${(summary.avg_latency_ms / 1000).toFixed(1)}s` : "—"} />
          <Tile label="Lỗi" value={summary.error_count} tone={summary.error_count ? "danger" : undefined} />
          <Tile label="👍 / 👎" value={`${summary.feedback_up} / ${summary.feedback_down}`} hint={`${Math.round(summary.feedback_rate * 100)}% có đánh giá`} tone={summary.feedback_down > summary.feedback_up ? "warn" : undefined} />
        </div>
      )}

      {summary && summary.top_documents.length > 0 && (
        <div className="rounded-xl px-4 py-3 mb-5 text-xs flex flex-wrap items-center gap-2" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
          <span className="font-semibold" style={{ color: "var(--muted)" }}>Văn bản được trích dẫn nhiều nhất:</span>
          {summary.top_documents.map((d) => (
            <span key={d.filename} className="rounded-md px-2 py-1" style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>
              {d.filename.replace(/\.(txt|pdf|docx)$/i, "")} <strong>×{d.count}</strong>
            </span>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="grid gap-2 mb-4 md:grid-cols-6">
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
        <select value={query.channel || ""} onChange={(e) => set({ channel: (e.target.value || "") as AuditQuery["channel"] })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Mọi kênh</option>
          <option value="staff">Cán bộ</option>
          <option value="customer">Khách hàng</option>
          <option value="admin_test">Admin thử nghiệm</option>
          <option value="embed">Website nhúng</option>
          <option value="extension">Browser extension</option>
          <option value="report">Báo cáo (chạy nền)</option>
          <option value="scheduled">Báo cáo theo lịch</option>
          <option value="form">Biểu mẫu</option>
        </select>
        <select value={query.rating || ""} onChange={(e) => set({ rating: (e.target.value || "") as AuditQuery["rating"] })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Mọi đánh giá</option>
          <option value="down">👎 Chưa hài lòng</option>
          <option value="up">👍 Hài lòng</option>
          <option value="none">Chưa đánh giá</option>
        </select>
        <select value={query.status || ""} onChange={(e) => set({ status: (e.target.value || "") as AuditQuery["status"] })}
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
          <option value="">Mọi trạng thái</option>
          <option value="completed">Thành công</option>
          <option value="failed">Lỗi</option>
          <option value="blocked">Bị chặn (bộ lọc an toàn)</option>
          <option value="waiting">Chờ cán bộ duyệt thao tác</option>
        </select>
        <input value={query.q || ""} onChange={(e) => set({ q: e.target.value })} placeholder="Tìm trong câu hỏi / trả lời…"
          className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
      </div>

      {error && <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>{error}</div>}

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 rounded-xl" style={{ border: "1px dashed var(--border)", background: "var(--card)" }}>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Chưa có lượt hỏi nào khớp bộ lọc.</p>
        </div>
      ) : (
        <div className="responsive-table-wrap rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                {["Thời gian", "Kênh", "Đơn vị / Trợ lý", "Người hỏi", "Câu hỏi", "Độ trễ", "Token", "Trạng thái", "Đánh giá"].map((h) => (
                  <th key={h} className="text-left px-3 py-2.5 font-semibold whitespace-nowrap" style={{ color: "var(--muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const ch = CHANNEL_STYLE[r.channel] || CHANNEL_STYLE.admin_test;
                const st = STATUS_STYLE[r.status] || STATUS_STYLE.running;
                return (
                  <tr key={r.id} className="cursor-pointer transition-colors" style={{ borderTop: "1px solid var(--border)" }}
                    onClick={() => openDetail(r.id)}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "var(--card-hover)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                    <td className="px-3 py-2.5 whitespace-nowrap" style={{ color: "var(--muted)" }}>{fmtTime(r.started_at)}</td>
                    <td className="px-3 py-2.5">
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={ch}>{CHANNEL_LABEL[r.channel] || r.channel}</span>
                      {r.client_origin && <div className="text-[10px] mt-0.5 truncate" style={{ color: "var(--muted)", maxWidth: 140 }} title={r.client_origin}>{r.client_origin.replace(/^https?:\/\//, "")}</div>}
                    </td>
                    <td className="px-3 py-2.5" style={{ color: "var(--foreground)" }}>
                      <div className="font-medium truncate" style={{ maxWidth: 200 }}>{r.app_name || (r.workflow_id ? "Luồng xử lý (thử)" : "Hỏi đáp kho tri thức")}</div>
                      <div className="text-[10px] truncate" style={{ color: "var(--muted)", maxWidth: 200 }}>{r.workspace_name || "—"}</div>
                    </td>
                    <td className="px-3 py-2.5" style={{ color: "var(--foreground)" }}>
                      <div className="truncate" style={{ maxWidth: 160 }}>{r.asked_by || "—"}</div>
                      {r.asked_by_meta && <div className="text-[10px] truncate" style={{ color: "var(--muted)", maxWidth: 160 }}>{r.asked_by_meta}</div>}
                    </td>
                    <td className="px-3 py-2.5" style={{ color: "var(--foreground)" }}>
                      <div className="truncate" style={{ maxWidth: 320 }} title={r.query_preview || ""}>{r.query_preview || "—"}</div>
                      {r.error && <div className="text-[10px] truncate" style={{ color: "#ef4444", maxWidth: 320 }}>{r.error}</div>}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap font-mono" style={{ color: r.latency_ms != null && r.latency_ms > 8000 ? "#f59e0b" : "var(--muted)" }}>
                      {r.latency_ms != null ? `${(r.latency_ms / 1000).toFixed(1)}s` : "—"}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap font-mono text-right" style={{ color: "var(--muted)" }}>
                      {r.total_tokens ? r.total_tokens.toLocaleString("vi-VN") : "—"}
                    </td>
                    <td className="px-3 py-2.5"><span className="rounded-full px-2 py-0.5 text-[10px] font-bold" style={{ background: st.bg, color: st.color }}>{st.label}</span></td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {r.feedback_rating === "up" && <span title={r.feedback_reason || ""}>👍</span>}
                      {r.feedback_rating === "down" && <span title={r.feedback_reason || ""} style={{ color: "#ef4444" }}>👎 {r.feedback_reason ? "✎" : ""}</span>}
                      {!r.feedback_rating && <span style={{ color: "var(--muted)" }}>—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail drawer */}
      {detail && (
        <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", justifyContent: "flex-end", background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)" }}
          onClick={() => setDetail(null)}>
          <div onClick={(e) => e.stopPropagation()} className="h-full overflow-y-auto p-6 w-full sm:w-[640px]"
            style={{ background: "var(--card)", borderLeft: "1px solid var(--border)" }}>
            <div className="flex items-start justify-between gap-3 mb-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>Chi tiết lượt hỏi</p>
                <h3 className="text-base font-semibold" style={{ color: "var(--foreground)" }}>{detail.app_name || "Hỏi đáp kho tri thức"}</h3>
                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  {fmtTime(detail.started_at)} · {CHANNEL_LABEL[detail.channel]}{detail.client_origin ? ` (${detail.client_origin})` : ""} · {detail.workspace_name || "—"} · {detail.latency_ms != null ? `${(detail.latency_ms / 1000).toFixed(1)}s` : "—"}
                </p>
              </div>
              <button onClick={() => setDetail(null)} className="rounded-lg px-2 py-1 text-xs" style={{ color: "var(--muted)", border: "1px solid var(--border)" }}>Đóng</button>
            </div>

            <Section title="Người hỏi">
              <p className="text-sm" style={{ color: "var(--foreground)" }}>{detail.asked_by || "—"}{detail.asked_by_meta ? ` — ${detail.asked_by_meta}` : ""}</p>
            </Section>

            <Section title="Câu hỏi">
              <p className="text-sm whitespace-pre-wrap rounded-lg px-3 py-2" style={{ background: "var(--accent-glow)", color: "var(--foreground)" }}>{detail.question || "—"}</p>
            </Section>

            <Section title="Câu trả lời">
              {detail.answer ? (
                <div className="text-sm rounded-lg px-3 py-2" style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
                  <Markdown accent="var(--accent)">{detail.answer}</Markdown>
                </div>
              ) : (
                <p className="text-sm rounded-lg px-3 py-2" style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444" }}>Không có câu trả lời. {detail.error || ""}</p>
              )}
            </Section>

            {detail.sources && detail.sources.length > 0 && (
              <Section title={`Nguồn trích dẫn (${detail.sources.length})`}>
                <div className="space-y-2">
                  {detail.sources.map((s, i) => (
                    <div key={s.chunk_id || i} className="rounded-lg px-3 py-2 text-xs" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                      <div className="font-semibold" style={{ color: "var(--accent)" }}>[#{i}] {sourceLabel(s) || "Tài liệu"}{typeof s.score === "number" ? ` · ${(s.score * 100).toFixed(0)}%` : ""}</div>
                      <div className="mt-1" style={{ color: "var(--muted)" }}>{sourceBody(s, 260)}{(s.content || "").length > 260 ? "…" : ""}</div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <Section title={`Token sử dụng${detail.total_tokens ? ` (${detail.total_tokens.toLocaleString("vi-VN")})` : ""}`}>
              {detail.usage.length === 0 ? <p className="text-sm" style={{ color: "var(--muted)" }}>Chưa ghi nhận token cho lượt này.</p> : (
                <div className="rounded-lg overflow-hidden text-xs" style={{ border: "1px solid var(--border)" }} data-testid="audit-usage">
                  {detail.usage.map((u) => {
                    const c = COMPONENTS.find((x) => x.key === u.key);
                    return (
                      <div key={u.key} className="flex items-center justify-between gap-3 px-3 py-1.5" style={{ borderTop: "1px solid var(--border)", background: "var(--background)" }}>
                        <span className="flex items-center gap-2" style={{ color: "var(--foreground)" }}>
                          <span className="rounded-sm" style={{ width: 8, height: 8, background: c?.color || "var(--accent)" }} />
                          {c?.label || u.key}{u.calls > 1 ? ` ×${u.calls}` : ""}{u.estimated_calls ? " ~" : ""}
                        </span>
                        <span className="font-mono" style={{ color: "var(--muted)" }}>
                          vào {u.prompt_tokens.toLocaleString("vi-VN")} · ra {u.completion_tokens.toLocaleString("vi-VN")} · <strong style={{ color: "var(--foreground)" }}>{u.total_tokens.toLocaleString("vi-VN")}</strong>
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </Section>

            <Section title="Đánh giá của người dùng">
              {detail.feedback_rating ? (
                <p className="text-sm" style={{ color: "var(--foreground)" }}>
                  {detail.feedback_rating === "up" ? "👍 Hài lòng" : "👎 Chưa hài lòng"}
                  {detail.feedback_reason && <span style={{ color: "var(--muted)" }}> — “{detail.feedback_reason}”</span>}
                </p>
              ) : <p className="text-sm" style={{ color: "var(--muted)" }}>Chưa có đánh giá.</p>}
            </Section>

            <Section title={`Các bước xử lý (${detail.steps.length})`}>
              {detail.steps.length === 0 ? <p className="text-sm" style={{ color: "var(--muted)" }}>Không có bước nào được ghi.</p> : (
                <ol className="space-y-2">
                  {detail.steps.map((s, i) => (
                    <li key={s.id} className="rounded-lg px-3 py-2 text-xs" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                      <div className="flex items-center justify-between">
                        <span style={{ color: "var(--foreground)" }}>
                          <span className="font-bold rounded px-1.5 py-0.5 mr-2" style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>{i + 1}</span>
                          <strong>{NODE_LABEL[s.node_type] || s.node_type}</strong> <span style={{ color: "var(--muted)" }}>({s.node_id})</span>
                        </span>
                        <span className="font-mono" style={{ color: "var(--muted)" }}>{s.duration_ms != null ? `${s.duration_ms}ms` : "…"}</span>
                      </div>
                      {(s.input_json || s.output_json) && (
                        <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[10px]" style={{ color: "var(--muted)" }}>
                          {JSON.stringify({ input: s.input_json, output: s.output_json }, null, 1).slice(0, 700)}
                        </pre>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </Section>
          </div>
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, hint, tone }: { label: string; value: string | number; hint?: string; tone?: "danger" | "warn" }) {
  const color = tone === "danger" ? "#ef4444" : tone === "warn" ? "#f59e0b" : "var(--foreground)";
  return (
    <div className="rounded-xl px-4 py-3" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
      <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: "var(--muted)" }}>{label}</p>
      <p className="text-xl font-semibold mt-0.5" style={{ color }}>{value}</p>
      {hint && <p className="text-[10px]" style={{ color: "var(--muted)" }}>{hint}</p>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <p className="text-[10px] font-bold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>{title}</p>
      {children}
    </div>
  );
}
