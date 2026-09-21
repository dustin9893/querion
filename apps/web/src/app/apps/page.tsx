"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/components/providers/I18nProvider";
import { AppResponse, AppAudience, createApp, listApps, deleteApp } from "@/lib/api/apps";
import { apiAssetUrl } from "@/lib/api";
import { WorkflowResponse, listWorkflows } from "@/lib/api/workflows";
import { DatasetResponse, listDatasets } from "@/lib/api/datasets";
import DatasetPicker, { blockedDatasets } from "@/components/datasets/DatasetPicker";

const fieldStyle = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

export default function AppsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [apps, setApps] = useState<AppResponse[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createWorkflowId, setCreateWorkflowId] = useState("");
  const [createDatasetIds, setCreateDatasetIds] = useState<string[]>([]);
  const [createAudience, setCreateAudience] = useState<AppAudience>("staff");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [a, w, d] = await Promise.all([listApps(), listWorkflows(), listDatasets()]);
      setApps(a);
      setWorkflows(w);
      setDatasets(d);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);


  const handleCreate = async () => {
    if (!createName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const app = await createApp({
        name: createName,
        workflow_id: createWorkflowId || undefined,
        dataset_ids: createDatasetIds,
        audience: createAudience,
      });
      router.push(`/apps/${app.id}`);
    } catch (err: any) {
      setCreateError(err.message || "Tạo trợ lý thất bại");
    } finally { setCreating(false); }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    try {
      await deleteApp(deleting);
      setApps((prev) => prev.filter((a) => a.id !== deleting));
    } catch { /* silent */ }
    finally { setDeleting(null); }
  };

  const deletingApp = apps.find((a) => a.id === deleting);

  return (
    <div>
      <div className="page-header flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>{t("title", "apps")}</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>{t("description", "apps")}</p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium"
          style={{ background: "var(--accent)", color: "#fff" }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          {t("createApp", "apps")}
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : apps.length === 0 ? (
        <div className="text-center py-20">
          <div className="rounded-full p-4 mb-4 mx-auto w-fit" style={{ background: "var(--accent-glow)" }}>
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ color: "var(--accent)" }}>
              <path d="M6 9H26M6 16H20M6 23H14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--foreground)" }}>{t("empty.title", "apps")}</h3>
          <p className="text-sm" style={{ color: "var(--muted)" }}>{t("empty.description", "apps")}</p>
        </div>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {apps.map((app) => {
            const wf = workflows.find((w) => w.id === app.workflow_id);
            const bound = (app.dataset_ids || []).map((id) => datasets.find((d) => d.id === id)).filter((d): d is DatasetResponse => !!d);
            const isCustomer = app.audience === "customer";
            return (
              <div key={app.id} onClick={() => router.push(`/apps/${app.id}`)}
                className="rounded-xl p-4 cursor-pointer transition-all group"
                style={{ background: "var(--card)", border: "1px solid var(--border)" }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}>
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    {app.logo_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={apiAssetUrl(app.logo_url) || ""} alt="" className="rounded-lg shrink-0" style={{ width: 28, height: 28, objectFit: "cover" }} />
                    ) : (
                      <div className="rounded-lg p-1.5 shrink-0" style={{ background: isCustomer ? "rgba(34,197,94,0.12)" : "var(--accent-glow)" }}>
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ color: isCustomer ? "#16a34a" : "var(--accent)" }}>
                          <path d="M3 4.5H13M3 8H10M3 11.5H8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                        </svg>
                      </div>
                    )}
                    <h3 className="text-sm font-semibold truncate" style={{ color: "var(--foreground)" }}>{app.name}</h3>
                  </div>
                  <button onClick={(e) => { e.stopPropagation(); setDeleting(app.id); }}
                    className="opacity-0 group-hover:opacity-100 rounded-lg p-1 transition-all shrink-0"
                    style={{ color: "var(--muted)" }}>
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M4 4L10 10M4 10L10 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" /></svg>
                  </button>
                </div>
                {app.description && <p className="text-xs mb-2 line-clamp-2" style={{ color: "var(--muted)" }}>{app.description}</p>}
                <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                  <span className="rounded-full px-2 py-0.5 font-bold uppercase tracking-wide"
                    style={{ background: isCustomer ? "rgba(34,197,94,0.12)" : "var(--accent-glow)", color: isCustomer ? "#16a34a" : "var(--accent)" }}>
                    {isCustomer ? "Khách hàng" : "Cán bộ"}
                  </span>
                  <span className="rounded-full px-2 py-0.5 font-semibold"
                    style={{ background: app.is_published ? "rgba(34,197,94,0.12)" : "rgba(120,120,120,0.15)", color: app.is_published ? "#22c55e" : "var(--muted)" }}>
                    {app.is_published ? "Đã công bố" : "Nháp"}
                  </span>
                  {!isCustomer && app.share_scope === "bank" && (
                    <span className="rounded-full px-2 py-0.5 font-semibold" style={{ background: "rgba(59,130,246,0.12)", color: "#2563eb" }}>Toàn ngân hàng</span>
                  )}
                  {wf && <span className="rounded-full px-2 py-0.5" style={{ background: "var(--background)", color: "var(--muted)", border: "1px solid var(--border)" }}>⚙ {wf.name}</span>}
                  {bound.slice(0, 2).map((ds) => (
                    <span key={ds.id} className="rounded-full px-2 py-0.5" style={{ background: "var(--background)", color: "var(--muted)", border: "1px solid var(--border)" }}>📚 {ds.name}</span>
                  ))}
                  {bound.length > 2 && <span className="rounded-full px-2 py-0.5" style={{ background: "var(--background)", color: "var(--muted)", border: "1px solid var(--border)" }} title={bound.slice(2).map((d) => d.name).join(", ")}>+{bound.length - 2} kho</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
          onClick={() => setShowCreate(false)}>
          <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-6"
            style={{ background: "var(--card)", border: "1px solid var(--border)", width: 480 }}>
            <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--foreground)" }}>Tạo trợ lý mới</h3>
            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Tên trợ lý</label>
                <input value={createName} onChange={(e) => setCreateName(e.target.value)} placeholder="VD: Trợ lý Tín dụng KHDN"
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" autoFocus style={fieldStyle} />
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Đối tượng</label>
                <div className="grid grid-cols-2 gap-2">
                  {([{ v: "staff", l: "Cán bộ nội bộ" }, { v: "customer", l: "Khách hàng (trang công khai)" }] as { v: AppAudience; l: string }[]).map((o) => (
                    <button key={o.v} type="button" onClick={() => { setCreateAudience(o.v); setCreateDatasetIds((ids) => (o.v === "customer" ? ids.filter((id) => !blockedDatasets(datasets, [id], "customer").length) : ids)); }}
                      className="rounded-lg px-3 py-2 text-xs font-semibold"
                      style={{ background: createAudience === o.v ? "var(--accent-glow)" : "var(--background)", border: `1px solid ${createAudience === o.v ? "var(--accent)" : "var(--border)"}`, color: createAudience === o.v ? "var(--accent-hover)" : "var(--foreground)" }}>
                      {o.l}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Kho tri thức (RAG) — chọn một hoặc nhiều</label>
                <div className="overflow-y-auto pr-1" style={{ maxHeight: 220 }}>
                  <DatasetPicker datasets={datasets} value={createDatasetIds} onChange={setCreateDatasetIds} audience={createAudience} compact />
                </div>
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Luồng xử lý (tuỳ chọn)</label>
                <select value={createWorkflowId} onChange={(e) => setCreateWorkflowId(e.target.value)}
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
                  <option value="">Không — trả lời trực tiếp bằng RAG</option>
                  {workflows.filter((wf) => wf.type !== "report").map((wf) => <option key={wf.id} value={wf.id}>{wf.name}</option>)}
                </select>
              </div>
              {createError && <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>{createError}</div>}
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setShowCreate(false)} className="rounded-lg px-4 py-2 text-xs font-medium"
                style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>Huỷ</button>
              <button onClick={handleCreate} disabled={creating || !createName.trim()}
                className="rounded-lg px-4 py-2 text-xs font-medium"
                style={{ background: "var(--accent)", color: "#fff" }}>{creating ? "..." : "Tạo"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Modal */}
      {deleting && (
        <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
          onClick={() => setDeleting(null)}>
          <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-6"
            style={{ background: "var(--card)", border: "1px solid var(--border)", width: 400 }}>
            <div className="flex items-center gap-3 mb-4">
              <div className="rounded-full p-2" style={{ background: "rgba(239,68,68,0.1)" }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style={{ color: "#ef4444" }}>
                  <path d="M10 6V10M10 14H10.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>Xoá trợ lý</h3>
                <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>Xoá <strong>{deletingApp?.name}</strong>? Hội thoại và nhật ký liên quan sẽ mất liên kết.</p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleting(null)} className="rounded-lg px-4 py-2 text-xs font-medium"
                style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>Huỷ</button>
              <button onClick={confirmDelete} className="rounded-lg px-4 py-2 text-xs font-medium"
                style={{ background: "#ef4444", color: "#fff" }}>Xoá</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
