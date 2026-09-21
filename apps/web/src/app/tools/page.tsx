"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePermission } from "@/components/providers/AuthProvider";
import { WorkflowResponse, listWorkflows } from "@/lib/api/workflows";
import {
  BuiltinTool, KIND_LABEL, ToolInput, ToolKind, ToolResponse,
  createTool, deleteTool, listBuiltins, listTools, testTool, updateTool,
} from "@/lib/api/tools";

/**
 * Công cụ (tools) của đơn vị: what assistants may call. Five kinds — an internal REST API, a
 * built-in calculation, an MCP server, a report workflow, or the generic Excel exporter that
 * turns whatever the conversation holds into a file. Secrets are write-only, so the form shows
 * only whether one is stored; the report and export kinds have no endpoint of their own.
 */

const field = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

const EMPTY: ToolInput & { secret?: string } = {
  slug: "", name: "", description: "", kind: "http",
  config: {}, params_schema: {}, requires_approval: false, allow_customer: false,
  share_scope: "unit", timeout_sec: 10,
};

const SAMPLE_SCHEMA = `{
  "type": "object",
  "properties": {
    "ma_ho_so": { "type": "string", "description": "Mã hồ sơ, vd HS2026-0412" }
  },
  "required": ["ma_ho_so"]
}`;

function pretty(v: unknown): string {
  // an HTTP tool returns the endpoint's raw body: show JSON bodies indented, not as an escaped string
  if (typeof v === "string") {
    try { return JSON.stringify(JSON.parse(v), null, 2); } catch { return v; }
  }
  try { return JSON.stringify(v ?? {}, null, 2); } catch { return "{}"; }
}

export default function ToolsPage() {
  const { canEdit, isOwner } = usePermission();
  const [tools, setTools] = useState<ToolResponse[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [builtins, setBuiltins] = useState<BuiltinTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState<ToolResponse | null>(null);
  const [form, setForm] = useState<ToolInput & { secret?: string }>(EMPTY);
  const [schemaText, setSchemaText] = useState("{}");
  const [configText, setConfigText] = useState("{}");
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);

  const [testFor, setTestFor] = useState<ToolResponse | null>(null);
  const [testArgs, setTestArgs] = useState("{}");
  const [testOut, setTestOut] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, b, w] = await Promise.all([listTools(), listBuiltins(), listWorkflows().catch(() => [])]);
      setTools(t); setBuiltins(b); setWorkflows(w); setError(null);
    } catch (e: any) { setError(e.message || "Không tải được danh sách công cụ"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditing(null); setForm({ ...EMPTY }); setSchemaText(SAMPLE_SCHEMA);
    setConfigText(pretty({ url: "https://core-api.msb.local/v1/ho-so/{{ma_ho_so}}", method: "GET", secret_header: "Authorization", secret_prefix: "Bearer " }));
    setShowForm(true);
  };

  const openEdit = (t: ToolResponse) => {
    setEditing(t);
    setForm({ slug: t.slug, name: t.name, description: t.description, kind: t.kind, requires_approval: t.requires_approval,
              allow_customer: t.allow_customer, share_scope: t.share_scope, timeout_sec: t.timeout_sec, is_active: t.is_active });
    setSchemaText(pretty(t.params_schema)); setConfigText(pretty(t.config));
    setShowForm(true);
  };

  const save = async () => {
    setSaving(true); setError(null);
    try {
      let config: Record<string, any> = {};
      let params: Record<string, any> = {};
      if (form.kind === "builtin") {
        config = { fn: (form.config as any)?.fn || builtins[0]?.fn };
      } else if (form.kind === "report") {
        // the workflow comes from the select, not the JSON box
        config = { workflow_id: (form.config as any)?.workflow_id || "" };
      } else if (form.kind === "export") {
        config = { format: "xlsx" };
      } else {
        config = JSON.parse(configText || "{}");
        if (form.kind === "http") params = JSON.parse(schemaText || "{}");
      }
      const payload: ToolInput = {
        name: form.name, description: form.description, config,
        requires_approval: form.requires_approval, allow_customer: form.allow_customer,
        share_scope: form.share_scope, timeout_sec: form.timeout_sec,
        ...(form.kind === "http" ? { params_schema: params } : {}),
        ...(form.secret !== undefined ? { secret: form.secret } : {}),
      };
      if (editing) await updateTool(editing.id, payload);
      else await createTool({ ...payload, slug: form.slug, kind: form.kind });
      setShowForm(false);
      await load();
    } catch (e: any) {
      setError(e instanceof SyntaxError ? "JSON không hợp lệ trong phần cấu hình hoặc tham số" : (e.message || "Lưu thất bại"));
    } finally { setSaving(false); }
  };

  const remove = async (t: ToolResponse) => {
    if (!confirm(`Xoá công cụ "${t.name}"? Các trợ lý đang gắn sẽ mất công cụ này.`)) return;
    try { await deleteTool(t.id); await load(); }
    catch (e: any) { setError(e.message || "Xoá thất bại"); }
  };

  const runTest = async () => {
    if (!testFor) return;
    setTesting(true); setTestOut(null);
    try {
      const r = await testTool(testFor.id, JSON.parse(testArgs || "{}"));
      setTestOut(r.ok ? pretty(r.result) : `⚠️ ${r.error}`);
    } catch (e: any) {
      setTestOut(`⚠️ ${e instanceof SyntaxError ? "Tham số không phải JSON hợp lệ" : e.message}`);
    } finally { setTesting(false); }
  };

  const reportWorkflows = useMemo(() => workflows.filter((w) => w.type === "report"), [workflows]);

  const builtinChoice = useMemo(() => builtins.find((b) => b.fn === (form.config as any)?.fn) || builtins[0], [builtins, form.config]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Công cụ</h2>
          <p className="text-sm mt-1 max-w-3xl" style={{ color: "var(--muted)" }}>
            Trợ lý có thể gọi công cụ để lấy dữ liệu thật hoặc tính toán, thay vì chỉ đọc tài liệu.
            Công cụ thuộc đơn vị này; chủ đơn vị có thể mở cho toàn ngân hàng.
          </p>
        </div>
        {canEdit && (
          <button onClick={openCreate} className="rounded-xl px-4 py-2.5 text-sm font-medium text-white shrink-0" style={{ background: "var(--accent)" }}>
            + Tạo công cụ
          </button>
        )}
      </div>

      <p className="text-[11px] mb-4" style={{ color: "var(--muted)" }}>
        Kết quả công cụ được coi là dữ liệu tra cứu, không phải chỉ dẫn cho mô hình. Khoá bí mật lưu mã hoá và không bao giờ hiển thị lại.
        Công cụ đánh dấu <strong>cần duyệt</strong> sẽ dừng lại chờ cán bộ xác nhận trước khi chạy.
      </p>

      {error && <p className="mb-3 text-sm rounded-lg px-3 py-2" style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)" }}>{error}</p>}

      {loading ? (
        <p className="text-sm" style={{ color: "var(--muted)" }}>Đang tải…</p>
      ) : tools.length === 0 ? (
        <div className="text-center py-20 rounded-xl" style={{ border: "1px dashed var(--border)" }}>
          <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--foreground)" }}>Chưa có công cụ nào</h3>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Tạo công cụ gọi API nội bộ, dùng phép tính sẵn có, hoặc kết nối MCP server.</p>
        </div>
      ) : (
        <div className="rounded-xl overflow-hidden responsive-table-wrap" style={{ border: "1px solid var(--border)" }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: "var(--card)" }}>
                {["Công cụ", "Loại", "Phạm vi", "Trợ lý dùng", "Trạng thái", ""].map((h, i) => (
                  <th key={h || i} className="text-left px-4 py-2.5 font-semibold" style={{ color: "var(--muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tools.map((t) => (
                <tr key={t.id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`tool-${t.slug}`}>
                  <td className="px-4 py-2.5">
                    <p className="font-medium" style={{ color: "var(--foreground)" }}>{t.name}</p>
                    <p className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{t.slug}</p>
                    <p className="line-clamp-1 max-w-md" style={{ color: "var(--muted)" }}>{t.description}</p>
                  </td>
                  <td className="px-4 py-2.5 whitespace-nowrap" style={{ color: "var(--muted)" }}>{KIND_LABEL[t.kind]}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {t.share_scope === "bank" && <Badge color="#2563eb" bg="rgba(59,130,246,0.12)">Toàn ngân hàng</Badge>}
                      {t.allow_customer && <Badge color="#16a34a" bg="rgba(34,197,94,0.12)">Khách hàng</Badge>}
                      {t.requires_approval && <Badge color="#b45309" bg="rgba(245,158,11,0.14)">Cần duyệt</Badge>}
                      {t.has_secret && <Badge color="var(--muted)" bg="var(--background)">🔑 có khoá</Badge>}
                      {!t.own_unit && <Badge color="var(--muted)" bg="var(--background)">của đơn vị khác</Badge>}
                    </div>
                  </td>
                  <td className="px-4 py-2.5" style={{ color: "var(--muted)" }}>{t.used_by}</td>
                  <td className="px-4 py-2.5">
                    <Badge color={t.is_active ? "#22c55e" : "#ef4444"} bg={t.is_active ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)"}>
                      {t.is_active ? "Đang bật" : "Tắt"}
                    </Badge>
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => { setTestFor(t); setTestArgs(pretty(exampleArgs(t.params_schema))); setTestOut(null); }}
                      className="text-xs px-2 py-1 rounded mr-1" style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>Chạy thử</button>
                    {canEdit && t.own_unit && (
                      <>
                        <button onClick={() => openEdit(t)} className="text-xs px-2 py-1 rounded mr-1" style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>Sửa</button>
                        <button onClick={() => remove(t)} className="text-xs px-2 py-1 rounded" style={{ color: "#ef4444" }}>Xoá</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ---- create / edit ---- */}
      {showForm && (
        <Modal onClose={() => setShowForm(false)} title={editing ? `Sửa công cụ: ${editing.name}` : "Tạo công cụ"}>
          <div className="space-y-3">
            {!editing && (
              <div className="grid grid-cols-3 gap-2">
                {(["http", "builtin", "mcp", "report", "export"] as ToolKind[]).map((k) => (
                  <button key={k} type="button" onClick={() => setForm((f) => ({ ...f, kind: k, config: {} }))}
                    data-testid={`kind-${k}`}
                    className="rounded-lg px-3 py-2 text-xs text-left"
                    style={{ background: form.kind === k ? "var(--accent-glow)" : "var(--background)", border: `1px solid ${form.kind === k ? "var(--accent)" : "var(--border)"}`, color: "var(--foreground)" }}>
                    <span className="block font-semibold">{KIND_LABEL[k]}</span>
                    <span className="block mt-0.5" style={{ color: "var(--muted)" }}>
                      {k === "http" ? "Gọi REST API, có khoá bí mật"
                        : k === "builtin" ? "Chạy nội bộ, không ra mạng"
                        : k === "mcp" ? "Nạp nhiều công cụ từ một server"
                        : k === "report" ? "Chạy một luồng báo cáo có sẵn"
                        : "Xuất bảng trong hội thoại ra .xlsx"}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {form.kind === "export" ? (
              <Field label="Định dạng tệp">
                <div className="rounded-lg px-3 py-2 text-sm" style={{ ...field, color: "var(--foreground)" }} data-testid="export-format">
                  Excel (.xlsx)
                </div>
                <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
                  Công cụ dùng chung, không gắn với báo cáo nào: mô hình tự dựng sheet, cột và dòng từ
                  đúng nội dung đang trao đổi rồi trả tệp để tải ngay trong khung chat. Tham số do hệ
                  thống quy định sẵn nên không cần khai báo JSON Schema.
                </p>
              </Field>
            ) : form.kind === "report" ? (
              <Field label="Luồng báo cáo">
                <select value={(form.config as any)?.workflow_id || ""}
                  onChange={(e) => setForm((f) => ({ ...f, config: { workflow_id: e.target.value } }))}
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={field} data-testid="report-workflow">
                  <option value="">— chọn luồng báo cáo —</option>
                  {reportWorkflows.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>
                <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
                  Trợ lý sẽ chạy luồng này khi cán bộ yêu cầu báo cáo, rồi trả tệp ngay trong khung chat.
                  Tham số lấy theo node đầu vào của luồng. {reportWorkflows.length === 0 && "Đơn vị chưa có luồng báo cáo nào."}
                </p>
              </Field>
            ) : form.kind === "builtin" ? (
              <Field label="Phép tính">
                <select value={(form.config as any)?.fn || builtins[0]?.fn || ""}
                  onChange={(e) => setForm((f) => ({ ...f, config: { fn: e.target.value } }))}
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={field} data-testid="builtin-fn">
                  {builtins.map((b) => <option key={b.fn} value={b.fn}>{b.name}</option>)}
                </select>
                {builtinChoice && <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>{builtinChoice.description}</p>}
              </Field>
            ) : (
              <Field label={form.kind === "mcp" ? "Cấu hình MCP server (JSON)" : "Cấu hình endpoint (JSON)"}>
                <textarea value={configText} onChange={(e) => setConfigText(e.target.value)} rows={form.kind === "mcp" ? 5 : 7}
                  className="w-full text-xs font-mono rounded-lg px-3 py-2 outline-none" style={field} data-testid="tool-config" />
                <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
                  {form.kind === "mcp"
                    ? 'Ví dụ: {"transport": "streamable_http", "url": "https://mcp.noi-bo/mcp"}. Tên công cụ sẽ có tiền tố là slug.'
                    : "Dùng {{ten_tham_so}} trong url, query hoặc body để chèn tham số. Khoá bí mật được ghép vào header phía máy chủ."}
                </p>
              </Field>
            )}

            {!editing && (
              <Field label="Slug (tên hàm gửi cho mô hình)">
                <input value={form.slug} onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
                  placeholder="tra_ho_so" className="w-full text-sm rounded-lg px-3 py-2 outline-none font-mono" style={field} data-testid="tool-slug" />
              </Field>
            )}
            <Field label="Tên hiển thị">
              <input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Tra hồ sơ tín dụng" className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={field} data-testid="tool-name" />
            </Field>
            <Field label="Mô tả (mô hình đọc phần này để quyết định có gọi hay không)">
              <textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} rows={2}
                placeholder="Tra trạng thái, khách hàng và hạn xử lý của hồ sơ tín dụng theo mã hồ sơ, ví dụ HS2026-0412."
                className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={field} data-testid="tool-description" />
            </Field>

            {form.kind === "http" && (
              <Field label="Tham số (JSON Schema)">
                <textarea value={schemaText} onChange={(e) => setSchemaText(e.target.value)} rows={7}
                  className="w-full text-xs font-mono rounded-lg px-3 py-2 outline-none" style={field} data-testid="tool-schema" />
              </Field>
            )}

            {form.kind !== "builtin" && form.kind !== "export" && form.kind !== "report" && (
              <Field label={editing?.has_secret ? "Khoá bí mật (đã lưu — nhập để thay, để trống giữ nguyên)" : "Khoá bí mật (tuỳ chọn)"}>
                <input type="password" value={form.secret ?? ""} onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value }))}
                  placeholder="token gọi API nội bộ" className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={field} />
              </Field>
            )}

            <div className="grid grid-cols-2 gap-3">
              <Check label="Cần cán bộ duyệt trước khi chạy" hint="Dùng cho thao tác ghi dữ liệu"
                checked={!!form.requires_approval} onChange={(v) => setForm((f) => ({ ...f, requires_approval: v }))} testid="tool-approval-flag" />
              <Check label="Cho phép kênh khách hàng" hint={isOwner ? "Chỉ bật với dữ liệu công khai" : "Chỉ chủ đơn vị được bật"}
                checked={!!form.allow_customer} disabled={!isOwner} onChange={(v) => setForm((f) => ({ ...f, allow_customer: v }))} />
              <Check label="Mở cho toàn ngân hàng" hint={isOwner ? "Đơn vị khác cũng gắn được" : "Chỉ chủ đơn vị được bật"}
                checked={form.share_scope === "bank"} disabled={!isOwner} onChange={(v) => setForm((f) => ({ ...f, share_scope: v ? "bank" : "unit" }))} />
              <Field label="Timeout (giây)">
                <input type="number" min={1} max={60} value={form.timeout_sec ?? 10}
                  onChange={(e) => setForm((f) => ({ ...f, timeout_sec: Number(e.target.value) }))}
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={field} />
              </Field>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <button onClick={() => setShowForm(false)} className="rounded-lg px-4 py-2 text-xs" style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>Huỷ</button>
            <button onClick={save} disabled={saving} className="rounded-lg px-4 py-2 text-xs font-medium text-white" style={{ background: "var(--accent)" }} data-testid="tool-save">
              {saving ? "Đang lưu…" : editing ? "Lưu" : "Tạo"}
            </button>
          </div>
        </Modal>
      )}

      {/* ---- test run ---- */}
      {testFor && (
        <Modal onClose={() => setTestFor(null)} title={`Chạy thử: ${testFor.name}`}>
          <p className="text-[11px] mb-2" style={{ color: "var(--muted)" }}>
            Gọi thật công cụ với tham số bên dưới. Tham số theo JSON Schema đã khai báo.
          </p>
          <ParamList schema={testFor.params_schema} />
          <textarea value={testArgs} onChange={(e) => setTestArgs(e.target.value)} rows={5}
            className="w-full text-xs font-mono rounded-lg px-3 py-2 outline-none" style={field} data-testid="test-args" />
          <button onClick={runTest} disabled={testing} className="mt-2 rounded-lg px-4 py-2 text-xs font-medium text-white" style={{ background: "var(--accent)" }} data-testid="test-run">
            {testing ? "Đang gọi…" : "Chạy"}
          </button>
          {testOut && (
            <pre className="mt-3 text-[11px] rounded-lg p-3 overflow-auto max-h-72 whitespace-pre-wrap break-words" style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }} data-testid="test-result">
              {testOut}
            </pre>
          )}
        </Modal>
      )}
    </div>
  );
}

/** A starting JSON for the test dialog: every declared parameter with its default, example or an empty value. */
function exampleArgs(schema: Record<string, any> | null | undefined): Record<string, unknown> {
  const props: Record<string, any> = schema?.properties || {};
  const empty: Record<string, unknown> = { string: "", integer: 0, number: 0, boolean: false, array: [], object: {} };
  return Object.fromEntries(Object.entries(props).map(([name, p]) => [
    name,
    p?.default ?? p?.examples?.[0] ?? p?.enum?.[0] ?? empty[p?.type] ?? "",
  ]));
}

function ParamList({ schema }: { schema: Record<string, any> | null | undefined }) {
  const props = Object.entries<any>(schema?.properties || {});
  if (!props.length) return null;
  const required = new Set<string>(schema?.required || []);
  return (
    <ul className="mb-2 space-y-0.5 text-[11px]" style={{ color: "var(--muted)" }} data-testid="test-params">
      {props.map(([name, p]) => (
        <li key={name}>
          <code style={{ color: "var(--foreground)" }}>{name}</code>
          {required.has(name) && <span style={{ color: "var(--accent)" }}> *</span>}
          {p?.type && <span> · {p.type}</span>}
          {p?.description && <span> — {p.description}</span>}
        </li>
      ))}
    </ul>
  );
}

function Badge({ children, color, bg }: { children: React.ReactNode; color: string; bg: string }) {
  return <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap" style={{ color, background: bg }}>{children}</span>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>{label}</label>
      {children}
    </div>
  );
}

function Check({ label, hint, checked, onChange, disabled, testid }: {
  label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; testid?: string;
}) {
  return (
    <label className="flex items-start gap-2 text-xs" style={{ opacity: disabled ? 0.55 : 1 }}>
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} className="mt-0.5" data-testid={testid} />
      <span>
        <span className="block font-medium" style={{ color: "var(--foreground)" }}>{label}</span>
        {hint && <span className="block" style={{ color: "var(--muted)" }}>{hint}</span>}
      </span>
    </label>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)", padding: 16 }}
      onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-5 overflow-y-auto"
        style={{ background: "var(--card)", border: "1px solid var(--border)", width: 620, maxWidth: "100%", maxHeight: "90vh" }}>
        <h3 className="text-sm font-semibold mb-3" style={{ color: "var(--foreground)" }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}
