"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  StaffForm, StaffFormField, downloadStaffReport, listStaffForms, prefillStaffForm,
  restoreStaffToken, staffMe, staffRefresh, submitStaffForm, suggestStaffFormField, EmployeeInfo,
} from "@/lib/api/staff";
import { useStaffSettings, getThemeVars } from "@/components/providers/StaffSettingsProvider";
import { BRAND_NAME } from "@/lib/brand";

/** Fill a business form: prefill from the core system, let AI draft the free text, export .docx. */
export default function StaffFormsPage() {
  const router = useRouter();
  const { theme } = useStaffSettings();
  const vars = getThemeVars(theme);

  const [employee, setEmployee] = useState<EmployeeInfo | null>(null);
  const [forms, setForms] = useState<StaffForm[]>([]);
  const [active, setActive] = useState<StaffForm | null>(null);
  const [values, setValues] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ text: string; tone: "ok" | "err" } | null>(null);
  const [done, setDone] = useState<{ id: string; filename: string; title: string } | null>(null);

  const field = {
    background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}`,
  };

  const load = useCallback(async () => {
    try { setForms(await listStaffForms()); }
    catch (e: any) { setMsg({ text: e.message || "Không tải được biểu mẫu", tone: "err" }); }
  }, []);

  useEffect(() => {
    (async () => {
      if (!restoreStaffToken()) { router.replace("/staff/login"); return; }
      try { setEmployee(await staffMe()); }
      catch {
        if (!(await staffRefresh())) { router.replace("/staff/login"); return; }
        try { setEmployee(await staffMe()); } catch { router.replace("/staff/login"); return; }
      }
      await load();
    })();
  }, [router, load]);

  const openForm = (f: StaffForm) => {
    setActive(f);
    setDone(null);
    setMsg(null);
    const init: Record<string, any> = {};
    f.fields.forEach((x) => { init[x.name] = x.default ?? (x.type === "boolean" ? false : ""); });
    setValues(init);
  };

  const prefill = async () => {
    if (!active) return;
    const key = values[active.fields.find((f) => f.source === "tool") ? prefillKey(active) : ""] ?? "";
    setBusy("prefill"); setMsg(null);
    try {
      const res = await prefillStaffForm(active.id, String(key));
      setValues((v) => ({ ...v, ...res.values }));
      setMsg({ text: "Đã điền dữ liệu từ hệ thống lõi", tone: "ok" });
    } catch (e: any) { setMsg({ text: e.message || "Không lấy được dữ liệu", tone: "err" }); }
    finally { setBusy(null); }
  };

  const suggest = async (f: StaffFormField) => {
    if (!active) return;
    setBusy(f.name); setMsg(null);
    try {
      const res = await suggestStaffFormField(active.id, f.name, values);
      setValues((v) => ({ ...v, [f.name]: res.text }));
    } catch (e: any) { setMsg({ text: e.message || "Không gợi ý được", tone: "err" }); }
    finally { setBusy(null); }
  };

  const submit = async () => {
    if (!active) return;
    setBusy("submit"); setMsg(null);
    try {
      const res = await submitStaffForm(active.id, values);
      setDone({ id: res.artifact_id, filename: res.filename, title: res.title });
      setMsg({ text: "Đã lập biểu mẫu", tone: "ok" });
    } catch (e: any) { setMsg({ text: e.message || "Không lập được biểu mẫu", tone: "err" }); }
    finally { setBusy(null); }
  };

  return (
    <div style={{ minHeight: "100vh", background: vars["--s-bg"], color: vars["--s-text"] }}>
      <div className="mx-auto px-4 py-6" style={{ maxWidth: 900 }}>
        <div className="flex items-center justify-between mb-5">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: vars["--s-accent-text"] }}>{BRAND_NAME}</p>
            <h1 className="text-xl font-semibold">Biểu mẫu</h1>
            <p className="text-sm mt-0.5" style={{ color: vars["--s-text-muted"] }}>
              Lập biểu mẫu của {employee?.workspace_name || "đơn vị"}: nhập mã hồ sơ để điền sẵn, AI gợi ý phần nhận xét, xuất file Word.
            </p>
          </div>
          <button onClick={() => router.push("/staff/chat")} className="text-xs rounded-lg px-3 py-2 shrink-0"
            style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>← Hỏi đáp</button>
        </div>

        {msg && (
          <div className="rounded-lg px-3 py-2 mb-3 text-xs" data-testid="form-msg"
            style={{ background: msg.tone === "ok" ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.1)", color: msg.tone === "ok" ? "#16a34a" : "#ef4444" }}>
            {msg.text}
          </div>
        )}

        {!active ? (
          forms.length === 0 ? (
            <div className="text-center py-16 rounded-xl" style={{ border: `1px dashed ${vars["--s-border"]}` }}>
              <p className="text-sm" style={{ color: vars["--s-text-muted"] }}>Đơn vị chưa công bố biểu mẫu nào.</p>
            </div>
          ) : (
            <div className="space-y-2" data-testid="staff-form-list">
              {forms.map((f) => (
                <button key={f.id} onClick={() => openForm(f)} data-testid={`open-form-${f.id}`}
                  className="w-full text-left rounded-xl p-4"
                  style={{ background: vars["--s-bg-secondary"], border: `1px solid ${vars["--s-border"]}` }}>
                  <p className="text-sm font-semibold">📄 {f.name}</p>
                  <p className="text-[11px] mt-0.5" style={{ color: vars["--s-text-muted"] }}>{f.description || "—"}</p>
                  <p className="text-[11px] mt-1" style={{ color: vars["--s-text-muted"] }}>
                    {f.fields.length} trường{f.has_prefill ? ` · điền sẵn theo ${f.prefill_label}` : ""}
                  </p>
                </button>
              ))}
            </div>
          )
        ) : (
          <div className="rounded-xl p-4" style={{ background: vars["--s-bg-secondary"], border: `1px solid ${vars["--s-border"]}` }}>
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold">{active.name}</p>
              <button onClick={() => setActive(null)} className="text-xs rounded px-2 py-1"
                style={{ color: vars["--s-text-muted"], border: `1px solid ${vars["--s-border"]}` }}>← Danh sách</button>
            </div>

            {active.has_prefill && (
              <div className="rounded-lg p-3 mb-3" style={{ background: vars["--s-bg"], border: `1px solid ${vars["--s-border"]}` }}>
                <p className="text-[11px] mb-1.5" style={{ color: vars["--s-text-muted"] }}>
                  Nhập {active.prefill_label} rồi bấm “Điền sẵn” để lấy dữ liệu từ hệ thống lõi.
                </p>
                <div className="flex gap-2">
                  <input value={values[prefillKey(active)] ?? ""} data-testid="prefill-key"
                    onChange={(e) => setValues((v) => ({ ...v, [prefillKey(active)]: e.target.value }))}
                    placeholder="VD: HS2026-0412"
                    className="flex-1 text-sm rounded-lg px-3 py-2 outline-none" style={field} />
                  <button onClick={prefill} disabled={busy === "prefill"} data-testid="prefill-button"
                    className="text-xs rounded-lg px-3 py-2 font-medium whitespace-nowrap"
                    style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
                    {busy === "prefill" ? "Đang lấy..." : "Điền sẵn"}
                  </button>
                </div>
              </div>
            )}

            <div className="space-y-3" data-testid="form-body">
              {active.fields.map((f) => (
                <div key={f.name}>
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold" style={{ color: vars["--s-text-secondary"] }}>
                      {f.label}{f.required ? " *" : ""}
                      {f.source === "tool" && <span style={{ color: vars["--s-text-muted"] }}> · từ hệ thống</span>}
                      {f.pii && <span style={{ color: "#ef4444" }}> · không gửi cho AI</span>}
                    </label>
                    {f.source === "llm" && (
                      <button onClick={() => suggest(f)} disabled={busy === f.name} data-testid={`suggest-${f.name}`}
                        className="text-[11px] rounded px-2 py-0.5"
                        style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
                        {busy === f.name ? "Đang soạn..." : "✨ AI gợi ý"}
                      </button>
                    )}
                  </div>
                  {f.type === "text" ? (
                    <textarea value={values[f.name] ?? ""} rows={4} data-testid={`field-${f.name}`}
                      onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                      className="w-full text-sm rounded-lg px-3 py-2 outline-none resize-y mt-1" style={field} />
                  ) : f.type === "boolean" ? (
                    <label className="flex items-center gap-2 text-sm mt-1">
                      <input type="checkbox" checked={!!values[f.name]} data-testid={`field-${f.name}`}
                        onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.checked }))} />
                      {f.description || "Có"}
                    </label>
                  ) : f.type === "select" ? (
                    <select value={values[f.name] ?? ""} data-testid={`field-${f.name}`}
                      onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                      className="w-full text-sm rounded-lg px-3 py-2 outline-none mt-1" style={field}>
                      <option value="">—</option>
                      {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input type={f.type === "number" ? "number" : "text"} value={values[f.name] ?? ""}
                      data-testid={`field-${f.name}`} placeholder={f.description || ""}
                      onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                      className="w-full text-sm rounded-lg px-3 py-2 outline-none mt-1" style={field} />
                  )}
                </div>
              ))}
            </div>

            <div className="flex items-center gap-2 mt-4">
              <button onClick={submit} disabled={busy === "submit"} data-testid="submit-form"
                className="rounded-lg px-4 py-2 text-sm font-medium"
                style={{ background: vars["--s-accent"], color: "#fff" }}>
                {busy === "submit" ? "Đang tạo..." : "Xuất file Word"}
              </button>
              {done && (
                <button onClick={() => downloadStaffReport(done)} data-testid="download-filled"
                  className="rounded-lg px-4 py-2 text-sm font-medium"
                  style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
                  ⬇ Tải {done.filename}
                </button>
              )}
            </div>
            {done && (
              <p className="text-[11px] mt-2" style={{ color: vars["--s-text-muted"] }}>
                Bản vừa lập cũng nằm trong mục <button onClick={() => router.push("/staff/reports")} className="underline"
                  style={{ color: vars["--s-accent-text"] }}>Báo cáo của tôi</button>.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** The field the prefill tool is keyed by (declared on the form). */
function prefillKey(form: StaffForm): string {
  const byLabel = form.fields.find((f) => f.label === form.prefill_label);
  return byLabel?.name || form.fields[0]?.name || "";
}
