"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FIELD_SOURCE_LABEL, FIELD_TYPE_LABEL, FormField, FormResponse,
  createForm, deleteForm, listForms, renderFormPreview, updateForm, uploadFormTemplate,
} from "@/lib/api/forms";
import { ToolResponse, listTools } from "@/lib/api/tools";
import { downloadArtifact } from "@/lib/api/artifacts";

const field = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

const SOURCE_COLOR: Record<string, string> = { user: "var(--muted)", tool: "#0ea5e9", llm: "#a855f7" };

export default function FormsPage() {
  const [forms, setForms] = useState<FormResponse[]>([]);
  const [tools, setTools] = useState<ToolResponse[]>([]);
  const [selected, setSelected] = useState<FormResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [f, t] = await Promise.all([listForms(), listTools()]);
      setForms(f); setTools(t);
      setSelected((cur) => (cur ? f.find((x) => x.id === cur.id) || null : null));
    } catch (e: any) { setError(e.message || "Không tải được biểu mẫu"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const created = await createForm({
        name: "Biểu mẫu mới",
        fields: [{ name: "ma_ho_so", label: "Mã hồ sơ", type: "string", source: "user", required: true, pii: false }],
      });
      await load();
      setSelected(created);
    } catch (e: any) { setError(e.message || "Tạo biểu mẫu thất bại"); }
  };

  const remove = async (f: FormResponse) => {
    if (!confirm(`Xoá biểu mẫu "${f.name}"? Các tệp đã lập vẫn được giữ.`)) return;
    try { await deleteForm(f.id); setSelected(null); await load(); }
    catch (e: any) { setError(e.message || "Xoá thất bại"); }
  };

  return (
    <div>
      <div className="page-header flex items-center justify-between mb-5">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Biểu mẫu</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            Mẫu Word + danh sách trường. Cán bộ mở ở cổng nội bộ, điền sẵn từ hệ thống lõi, AI gợi ý phần tự luận, rồi xuất file.
          </p>
        </div>
        <button onClick={create} className="shrink-0 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-medium"
          style={{ background: "var(--accent)", color: "#fff" }} data-testid="new-form">+ Biểu mẫu mới</button>
      </div>

      {error && <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>{error}</div>}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : forms.length === 0 ? (
        <div className="text-center py-16 rounded-xl" style={{ border: "1px dashed var(--border)", background: "var(--card)" }}>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Chưa có biểu mẫu nào.</p>
        </div>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }} data-testid="form-list">
          {forms.map((f) => (
            <div key={f.id} className="rounded-xl p-4 cursor-pointer" onClick={() => setSelected(f)}
              style={{ background: "var(--card)", border: `1px solid ${selected?.id === f.id ? "var(--accent)" : "var(--border)"}` }}
              data-testid={`form-${f.id}`}>
              <div className="flex items-start justify-between gap-2">
                <span className="font-semibold text-sm" style={{ color: "var(--foreground)" }}>{f.name}</span>
                <span className="rounded-full px-2 py-0.5 text-[10px] font-bold shrink-0"
                  style={{ background: f.is_published ? "rgba(34,197,94,0.12)" : "rgba(107,114,128,0.14)", color: f.is_published ? "#22c55e" : "var(--muted)" }}>
                  {f.is_published ? "ĐÃ CÔNG BỐ" : "NHÁP"}
                </span>
              </div>
              <p className="text-xs mt-1 line-clamp-2" style={{ color: "var(--muted)" }}>{f.description || "—"}</p>
              <p className="text-[11px] mt-2" style={{ color: "var(--muted)" }}>
                {f.fields.length} trường · {f.has_template ? `mẫu: ${f.template_filename}` : "chưa có mẫu .docx"}
                {f.prefill_tool_id ? " · có điền sẵn" : ""}{!f.own_unit ? " · dùng chung" : ""}
              </p>
            </div>
          ))}
        </div>
      )}

      {selected && (
        <FormEditor form={selected} tools={tools} onClose={() => setSelected(null)}
          onChanged={load} onDelete={() => remove(selected)} />
      )}
    </div>
  );
}

function FormEditor({ form, tools, onClose, onChanged, onDelete }: {
  form: FormResponse; tools: ToolResponse[]; onClose: () => void; onChanged: () => Promise<void>; onDelete: () => void;
}) {
  const [name, setName] = useState(form.name);
  const [description, setDescription] = useState(form.description || "");
  const [fields, setFields] = useState<FormField[]>(form.fields);
  const [prefillTool, setPrefillTool] = useState(form.prefill_tool_id || "");
  const [prefillArg, setPrefillArg] = useState(form.prefill_arg || "");
  const [mapping, setMapping] = useState<Record<string, string>>(form.prefill_mapping || {});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setName(form.name); setDescription(form.description || ""); setFields(form.fields);
    setPrefillTool(form.prefill_tool_id || ""); setPrefillArg(form.prefill_arg || "");
    setMapping(form.prefill_mapping || {});
  }, [form]);

  const patchField = (i: number, patch: Partial<FormField>) =>
    setFields((prev) => prev.map((f, j) => (j === i ? { ...f, ...patch } : f)));

  const save = async (extra: Partial<Parameters<typeof updateForm>[1]> = {}) => {
    setBusy(true); setMsg(null);
    try {
      await updateForm(form.id, {
        name, description, fields, prefill_tool_id: prefillTool || null,
        prefill_arg: prefillArg || null, prefill_mapping: mapping, ...extra,
      });
      await onChanged();
      setMsg("Đã lưu");
      setTimeout(() => setMsg(null), 2500);
    } catch (e: any) { setMsg(e.message || "Lưu thất bại"); }
    finally { setBusy(false); }
  };

  const testRender = async () => {
    setBusy(true); setMsg(null);
    try {
      const sample: Record<string, any> = {};
      fields.forEach((f) => {
        sample[f.name] = f.type === "number" ? 1000000 : f.type === "boolean" ? true
          : f.type === "date" ? "01/01/2026" : `[${f.label}]`;
      });
      const res = await renderFormPreview(form.id, sample);
      await downloadArtifact({ id: res.artifact_id, filename: res.filename });
      setMsg("Đã tạo bản thử và tải về");
    } catch (e: any) { setMsg(e.message || "Không tạo được bản thử"); }
    finally { setBusy(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", justifyContent: "flex-end", background: "rgba(0,0,0,0.5)", backdropFilter: "blur(2px)" }}
      onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="h-full overflow-y-auto p-6 w-full sm:w-[680px]"
        style={{ background: "var(--card)", borderLeft: "1px solid var(--border)" }} data-testid="form-editor">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0 flex-1">
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-full text-base font-semibold bg-transparent outline-none" style={{ color: "var(--foreground)" }}
              data-testid="form-name" />
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Mô tả ngắn cho cán bộ"
              className="w-full text-xs mt-1 bg-transparent outline-none" style={{ color: "var(--muted)" }} />
          </div>
          <button onClick={onClose} className="rounded-lg px-2 py-1 text-xs shrink-0" style={{ color: "var(--muted)", border: "1px solid var(--border)" }}>Đóng</button>
        </div>

        {!form.own_unit && (
          <p className="text-xs rounded-lg px-3 py-2 mb-3" style={{ background: "rgba(59,130,246,0.1)", color: "#2563eb" }}>
            Biểu mẫu dùng chung của đơn vị khác — chỉ xem, không sửa được.
          </p>
        )}

        {/* Fields */}
        <Section title={`Các trường (${fields.length})`}>
          <div className="space-y-2" data-testid="form-fields">
            {fields.map((f, i) => (
              <div key={i} className="rounded-lg p-2.5 space-y-1.5" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                <div className="flex gap-1.5">
                  <input value={f.name} onChange={(e) => patchField(i, { name: e.target.value })} placeholder="ma_bien"
                    className="text-[11px] rounded px-2 py-1 outline-none font-mono" style={{ ...field, width: 130 }} />
                  <input value={f.label} onChange={(e) => patchField(i, { label: e.target.value })} placeholder="Nhãn"
                    className="flex-1 text-[11px] rounded px-2 py-1 outline-none" style={field} />
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <select value={f.type} onChange={(e) => patchField(i, { type: e.target.value as FormField["type"] })}
                    className="text-[11px] rounded px-1.5 py-1 outline-none" style={field}>
                    {Object.entries(FIELD_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  <select value={f.source} onChange={(e) => patchField(i, { source: e.target.value as FormField["source"] })}
                    className="text-[11px] rounded px-1.5 py-1 outline-none"
                    style={{ ...field, color: SOURCE_COLOR[f.source] }} data-testid={`field-source-${f.name}`}>
                    {Object.entries(FIELD_SOURCE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  <label className="flex items-center gap-1 text-[10px]" style={{ color: "var(--muted)" }}>
                    <input type="checkbox" checked={f.required} onChange={(e) => patchField(i, { required: e.target.checked })} /> bắt buộc
                  </label>
                  <label className="flex items-center gap-1 text-[10px]" style={{ color: f.pii ? "#ef4444" : "var(--muted)" }}
                    title="Dữ liệu nhạy cảm: không bao giờ gửi vào mô hình AI">
                    <input type="checkbox" checked={f.pii} onChange={(e) => patchField(i, { pii: e.target.checked })} /> nhạy cảm
                  </label>
                  <button onClick={() => setFields((prev) => prev.filter((_, j) => j !== i))}
                    className="ml-auto text-[10px]" style={{ color: "#ef4444" }}>Xoá</button>
                </div>
                {f.source === "llm" && (
                  <textarea value={f.llm_prompt || ""} onChange={(e) => patchField(i, { llm_prompt: e.target.value })}
                    rows={2} placeholder="Yêu cầu cho AI khi soạn nội dung trường này"
                    className="w-full text-[11px] rounded px-2 py-1 outline-none resize-y" style={field} />
                )}
                {f.type === "select" && (
                  <input value={(f.options || []).join(", ")} placeholder="giá trị 1, giá trị 2"
                    onChange={(e) => patchField(i, { options: e.target.value.split(",").map((o) => o.trim()).filter(Boolean) })}
                    className="w-full text-[11px] rounded px-2 py-1 outline-none" style={field} />
                )}
              </div>
            ))}
            <button onClick={() => setFields((prev) => [...prev, { name: `truong_${prev.length + 1}`, label: "", type: "string", source: "user", required: false, pii: false }])}
              className="w-full text-[11px] rounded-lg px-2 py-1.5" style={{ border: "1px dashed var(--border)", color: "var(--muted)" }}
              data-testid="add-form-field">+ Thêm trường</button>
          </div>
        </Section>

        {/* Prefill */}
        <Section title="Điền sẵn từ hệ thống (tuỳ chọn)">
          <div className="space-y-2">
            <select value={prefillTool} onChange={(e) => setPrefillTool(e.target.value)}
              className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={field} data-testid="prefill-tool">
              <option value="">— không dùng —</option>
              {tools.filter((t) => t.kind !== "mcp" && !t.requires_approval).map((t) => (
                <option key={t.id} value={t.id}>{t.name} ({t.slug})</option>
              ))}
            </select>
            {prefillTool && (
              <>
                <select value={prefillArg} onChange={(e) => setPrefillArg(e.target.value)}
                  className="w-full text-xs rounded-lg px-3 py-2 outline-none" style={field}>
                  <option value="">— trường dùng làm khoá tra cứu —</option>
                  {fields.map((f) => <option key={f.name} value={f.name}>{f.label || f.name}</option>)}
                </select>
                <p className="text-[11px]" style={{ color: "var(--muted)" }}>Gán dữ liệu trả về vào từng trường (đường dẫn JSON):</p>
                {fields.filter((f) => f.source === "tool").map((f) => (
                  <div key={f.name} className="flex items-center gap-2">
                    <span className="text-[11px] w-32 truncate" style={{ color: "var(--foreground)" }}>{f.label || f.name}</span>
                    <input value={mapping[f.name] || ""} placeholder="vd: khach_hang"
                      onChange={(e) => setMapping((m) => ({ ...m, [f.name]: e.target.value }))}
                      className="flex-1 text-[11px] rounded px-2 py-1 outline-none font-mono" style={field} />
                  </div>
                ))}
              </>
            )}
          </div>
        </Section>

        {/* Template */}
        <Section title="Mẫu Word (.docx)">
          <input type="file" accept=".docx" data-testid="form-template-upload"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              setBusy(true); setMsg(null);
              try { await uploadFormTemplate(form.id, file); await onChanged(); setMsg("Đã tải mẫu lên"); }
              catch (err: any) { setMsg(err?.message || "Tải mẫu thất bại"); }
              finally { setBusy(false); }
            }}
            className="w-full text-[11px]" style={{ color: "var(--muted)" }} />
          <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
            {form.has_template ? `Đang dùng: ${form.template_filename}` : "Chưa có mẫu"} · dùng {"{{ ten_truong }}"} trong file Word;
            có sẵn {"{{ today }} {{ time }} {{ can_bo }}"} · bộ lọc {"| tien | so | ngay"}
          </p>
        </Section>

        <div className="flex flex-wrap items-center gap-2 mt-5">
          <button onClick={() => save()} disabled={busy || !form.own_unit}
            className="rounded-lg px-4 py-2 text-xs font-medium" style={{ background: "var(--accent)", color: "#fff" }}
            data-testid="save-form">{busy ? "..." : "Lưu"}</button>
          <button onClick={() => save({ is_published: !form.is_published })} disabled={busy || !form.own_unit}
            className="rounded-lg px-4 py-2 text-xs font-medium"
            style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}
            data-testid="publish-form">{form.is_published ? "Gỡ công bố" : "Công bố cho cán bộ"}</button>
          <button onClick={testRender} disabled={busy || !form.has_template}
            className="rounded-lg px-4 py-2 text-xs font-medium"
            style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}
            data-testid="test-render">Xuất bản thử</button>
          <button onClick={onDelete} disabled={!form.own_unit} className="ml-auto rounded-lg px-4 py-2 text-xs font-medium"
            style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>Xoá</button>
        </div>
        {msg && <p className="text-xs mt-2" style={{ color: msg.startsWith("Đã") ? "#22c55e" : "#ef4444" }} data-testid="form-msg">{msg}</p>}
      </div>
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
