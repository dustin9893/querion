"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  AppResponse, AppAudience, AppShareScope, WidgetConfigInput, getApp, updateApp, regenerateApiKey, listRuns, getRunSteps,
  RunResponse, RunStepResponse, customerLink, embedSnippet, embedPreviewUrl, uploadAppLogo, deleteAppLogo } from "@/lib/api/apps";
import { WorkflowResponse, listWorkflows } from "@/lib/api/workflows";
import { apiAssetUrl } from "@/lib/api";
import { DatasetResponse, listDatasets } from "@/lib/api/datasets";
import DatasetPicker, { blockedDatasets } from "@/components/datasets/DatasetPicker";
import Toggle from "@/components/ui/Toggle";
import { usePermission } from "@/components/providers/AuthProvider";
import { KIND_LABEL, ToolResponse, listTools } from "@/lib/api/tools";
import { listSkills, type Skill } from "@/lib/api/skills";

const fieldStyle = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

const ORIGIN_RE = /^https?:\/\/[a-z0-9.-]+(:\d{2,5})?$/i;

export default function AppDetailPage() {
  const params = useParams();
  const router = useRouter();
  const appId = params.appId as string;

  const [app, setApp] = useState<AppResponse | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [runs, setRuns] = useState<RunResponse[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [steps, setSteps] = useState<RunStepResponse[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"key" | "link" | "snippet" | null>(null);
  const [tab, setTab] = useState<"config" | "tools" | "skills" | "embed" | "runs">("config");

  // Form state
  const [name, setName] = useState("");
  const [workflowId, setWorkflowId] = useState("");
  const [datasetIds, setDatasetIds] = useState<string[]>([]);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [description, setDescription] = useState("");
  const [isPublished, setIsPublished] = useState(false);
  const [audience, setAudience] = useState<AppAudience>("staff");
  const [shareScope, setShareScope] = useState<AppShareScope>("unit");
  const { canManageMembers: isOwner } = usePermission(); // owner or super admin

  // Tools state (saved with the form)
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [toolIds, setToolIds] = useState<string[]>([]);
  const [tools, setTools] = useState<ToolResponse[]>([]);
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [memoryEnabled, setMemoryEnabled] = useState(true);

  // Browser extension state (fourth surface, staff only)
  const [extensionEnabled, setExtensionEnabled] = useState(false);
  const [extensionHostsText, setExtensionHostsText] = useState("");

  // Embed state
  const [embedEnabled, setEmbedEnabled] = useState(false);
  const [origins, setOrigins] = useState<string[]>([]);
  const [newOrigin, setNewOrigin] = useState("");
  const [originError, setOriginError] = useState<string | null>(null);
  const [widget, setWidget] = useState<WidgetConfigInput>({});
  const [suggestionsText, setSuggestionsText] = useState("");
  const [previewNonce, setPreviewNonce] = useState(0);

  // Logo (saved immediately on pick — independent of the form's Save button)
  const [logoBusy, setLogoBusy] = useState(false);
  const [logoError, setLogoError] = useState<string | null>(null);

  const hydrate = useCallback((a: AppResponse) => {
    setApp(a);
    setName(a.name);
    setWorkflowId(a.workflow_id || "");
    setDatasetIds(a.dataset_ids || []);
    setSystemPrompt(a.system_prompt || "");
    setDescription(a.description || "");
    setIsPublished(a.is_published);
    setAudience(a.audience || "staff");
    setShareScope(a.share_scope || "unit");
    setAgentEnabled(!!a.agent_enabled);
    setToolIds(a.tool_ids || []);
    setSkillIds(a.skill_ids || []);
    setMemoryEnabled(a.memory_enabled !== false);
    setEmbedEnabled(!!a.embed_enabled);
    setOrigins(a.allowed_origins || []);
    setExtensionEnabled(!!a.extension_enabled);
    setExtensionHostsText((a.extension_hosts || []).join("\n"));
    setWidget(a.widget_config || {});
    setSuggestionsText((a.widget_config?.suggestions || []).join("\n"));
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [a, w, d] = await Promise.all([getApp(appId), listWorkflows(), listDatasets()]);
        hydrate(a);
        setWorkflows(w);
        setDatasets(d);
        listTools().then(setTools).catch(() => setTools([]));
        listSkills().then(setSkills).catch(() => setSkills([]));
      } catch { router.push("/apps"); }
    })();
  }, [appId]); // eslint-disable-line

  const fetchRuns = useCallback(async () => {
    try { setRuns(await listRuns(appId)); } catch { /* silent */ }
  }, [appId]);

  useEffect(() => { if (tab === "runs") fetchRuns(); }, [tab, fetchRuns]);

  const datasetBlocked = blockedDatasets(datasets, datasetIds, audience).length > 0;

  const buildWidget = (): WidgetConfigInput => ({
    ...widget,
    suggestions: suggestionsText.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 4),
  });

  // a report workflow is not in the select list, so keep it visible instead of hiding the binding
  const boundReportWorkflow = workflowId
    ? workflows.find((wf) => wf.id === workflowId && wf.type === "report")
    : undefined;

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateApp(appId, {
        name,
        workflow_id: workflowId || "",
        dataset_ids: datasetIds,
        system_prompt: systemPrompt,
        description,
        is_published: isPublished,
        audience,
        allowed_origins: origins,
        agent_enabled: agentEnabled,
        tool_ids: toolIds,
        skill_ids: skillIds,
        memory_enabled: memoryEnabled,
        widget_config: buildWidget(),
        embed_enabled: embedEnabled,
        extension_enabled: audience === "staff" ? extensionEnabled : false,
        extension_hosts: extensionHostsText.split("\n").map((h) => h.trim()).filter(Boolean).slice(0, 20),
        // only owners may change it — send it only when it actually changed so editors can still save
        ...(shareScope !== (app?.share_scope || "unit") ? { share_scope: shareScope } : {}),
      });
      hydrate(updated);
      setPreviewNonce((n) => n + 1);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: any) {
      setSaveError(err.message || "Lưu thất bại");
    } finally { setSaving(false); }
  };

  const handleLogoFile = async (file: File | null) => {
    if (!file) return;
    setLogoBusy(true); setLogoError(null);
    try {
      setApp(await uploadAppLogo(appId, file));   // only the app record: keep unsaved form edits
      setPreviewNonce((n) => n + 1);
    } catch (err: any) { setLogoError(err.message || "Tải logo thất bại"); }
    finally { setLogoBusy(false); }
  };
  const handleLogoRemove = async () => {
    setLogoBusy(true); setLogoError(null);
    try {
      setApp(await deleteAppLogo(appId));
      setPreviewNonce((n) => n + 1);
    } catch (err: any) { setLogoError(err.message || "Xoá logo thất bại"); }
    finally { setLogoBusy(false); }
  };

  const handleRegenKey = async () => {
    if (!confirm("Tạo lại API key? Key cũ, link khách hàng cũ và mọi bản nhúng đang dùng key cũ sẽ ngừng hoạt động.")) return;
    try {
      const updated = await regenerateApiKey(appId);
      hydrate(updated);
      setPreviewNonce((n) => n + 1);
    } catch { /* silent */ }
  };

  const copy = (what: "key" | "link" | "snippet") => {
    if (!app) return;
    const text = what === "key" ? app.api_key : what === "link" ? customerLink(app) : embedSnippet(app);
    navigator.clipboard.writeText(text);
    setCopied(what);
    setTimeout(() => setCopied(null), 2000);
  };

  const addOrigin = () => {
    const v = newOrigin.trim().replace(/\/+$/, "");
    if (!v) return;
    if (!ORIGIN_RE.test(v)) { setOriginError("Dạng đúng: https://ten-mien.vn hoặc http://localhost:8090 (không có đường dẫn)"); return; }
    if (origins.includes(v.toLowerCase())) { setOriginError("Origin đã có trong danh sách"); return; }
    setOrigins((o) => [...o, v.toLowerCase()]);
    setNewOrigin("");
    setOriginError(null);
  };

  const viewSteps = async (runId: string) => {
    setSelectedRun(runId);
    try { setSteps(await getRunSteps(runId)); } catch { setSteps([]); }
  };

  if (!app) return (
    <div className="flex justify-center py-16">
      <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
    </div>
  );

  const embedDirty = embedEnabled !== !!app.embed_enabled || JSON.stringify(origins) !== JSON.stringify(app.allowed_origins || []);

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => router.push("/apps")} className="rounded-lg p-1.5" style={{ color: "var(--muted)" }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M12 3L6 9L12 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>{app.name}</h2>
        <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide"
          style={{ background: app.audience === "customer" ? "rgba(34,197,94,0.12)" : "var(--accent-glow)", color: app.audience === "customer" ? "#16a34a" : "var(--accent)" }}>
          {app.audience === "customer" ? "Khách hàng" : "Cán bộ"}
        </span>
        {app.embed_enabled && (
          <span className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide" style={{ background: "rgba(59,130,246,0.12)", color: "#2563eb" }}>
            Đang nhúng · {app.allowed_origins.length} website
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-xl" style={{ background: "var(--card)", border: "1px solid var(--border)", width: "fit-content" }}>
        {(["config", "tools", "skills", "embed", "runs"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className="rounded-lg px-4 py-1.5 text-xs font-semibold transition-all"
            style={{ background: tab === t ? "var(--accent)" : "transparent", color: tab === t ? "#fff" : "var(--muted)" }}>
            {t === "config" ? "⚙️ Cấu hình" : t === "tools" ? `🔧 Công cụ (${toolIds.length})` : t === "skills" ? `🎯 Kỹ năng (${skillIds.length})` : t === "embed" ? "🧩 Nhúng vào website" : `📊 Nhật ký chạy (${runs.length})`}
          </button>
        ))}
      </div>

      {tab === "config" && (
        <div className="space-y-5">
          <Field label="Tên trợ lý">
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
          </Field>

          <Field label="Đối tượng sử dụng">
            <div className="grid grid-cols-2 gap-2">
              {([
                { v: "staff", label: "Cán bộ nội bộ", hint: "Đăng nhập cổng /staff, dùng kho nội bộ hoặc công khai" },
                { v: "customer", label: "Khách hàng", hint: "Trang công khai /kh/… không cần đăng nhập, chỉ dùng kho công khai" },
              ] as { v: AppAudience; label: string; hint: string }[]).map((o) => {
                const active = audience === o.v;
                return (
                  <button key={o.v} type="button" onClick={() => setAudience(o.v)}
                    className="rounded-lg px-3 py-2.5 text-left text-xs transition-all"
                    style={{ background: active ? "var(--accent-glow)" : "var(--background)", border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`, color: active ? "var(--accent-hover)" : "var(--foreground)" }}>
                    <span className="block font-semibold">{o.label}</span>
                    <span className="block mt-0.5" style={{ color: "var(--muted)" }}>{o.hint}</span>
                  </button>
                );
              })}
            </div>
          </Field>

          <Field label="Luồng xử lý gắn kèm (tuỳ chọn)">
            <p className="text-[11px] mb-1" style={{ color: "var(--muted)" }}>
              Luồng chạy cho MỌI tin nhắn. Luồng báo cáo không xuất hiện ở đây — muốn trợ lý lập báo cáo khi được hỏi,
              hãy tạo <a href="/tools" className="underline" style={{ color: "var(--accent)" }}>Công cụ</a> loại “Báo cáo” rồi gắn ở tab Công cụ.
            </p>
            <select value={workflowId} onChange={(e) => setWorkflowId(e.target.value)}
              className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
              <option value="">Không — trả lời trực tiếp bằng RAG</option>
              {/* an assistant bound before report workflows were ruled out still shows its own,
                  otherwise the select silently displays "Không" while the binding is still there */}
              {boundReportWorkflow && (
                <option value={boundReportWorkflow.id}>{boundReportWorkflow.name} (báo cáo — không dùng cho hội thoại)</option>
              )}
              {workflows.filter((wf) => wf.type !== "report").map((wf) => (
                <option key={wf.id} value={wf.id}>{wf.name} ({wf.type})</option>
              ))}
            </select>
            {boundReportWorkflow && (
              <p className="text-[11px] mt-1" style={{ color: "var(--accent)" }}>
                Trợ lý này còn gắn một luồng báo cáo từ trước. Trợ lý đang bỏ qua nó và trả lời như bình thường;
                chọn “Không” rồi lưu để gỡ hẳn.
              </p>
            )}
          </Field>

          <Field label={`Kho tri thức (RAG)${datasetIds.length ? ` · đã chọn ${datasetIds.length}` : ""}`}>
            <p className="text-[11px] mb-2" style={{ color: "var(--muted)" }}>
              {workflowId
                ? "Trợ lý đang dùng luồng xử lý: kho tri thức lấy theo từng bước của luồng, lựa chọn ở đây chỉ dùng khi bỏ luồng."
                : "Chọn một hoặc nhiều kho. Câu hỏi được tìm trên tất cả kho đã chọn và lấy các đoạn liên quan nhất; không chọn kho nào thì trợ lý trả lời không dùng tài liệu."}
            </p>
            <DatasetPicker datasets={datasets} value={datasetIds} onChange={setDatasetIds} audience={audience} />
          </Field>

          <Field label="System prompt (để trống = dùng guardrail mặc định theo đối tượng)">
            <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} rows={4}
              placeholder="Để trống để dùng bộ nguyên tắc mặc định: chỉ trả lời theo tài liệu, luôn trích dẫn [#n], không quyết định thay cán bộ, không lộ thông tin khách hàng…"
              className="w-full text-sm rounded-lg px-3 py-2 outline-none resize-y" style={fieldStyle} />
          </Field>

          <Field label="Mô tả (hiển thị cho cán bộ / khách hàng)">
            <input value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Trợ lý này trả lời về…"
              className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
          </Field>

          <Field label="Logo trợ lý (ảnh hoặc icon)">
            <div className="flex items-center gap-4">
              <div className="rounded-full shrink-0 flex items-center justify-center overflow-hidden"
                style={{ width: 64, height: 64, background: "var(--accent-glow)", border: "1px solid var(--border)" }}>
                {app?.logo_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={apiAssetUrl(app.logo_url) || ""} alt="Logo trợ lý" data-testid="admin-logo-preview" style={{ width: 64, height: 64, objectFit: "cover" }} />
                ) : (
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" style={{ color: "var(--accent)" }}>
                    <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.2 3.4c-.5.4-1.3 0-1.3-.6V16A2.5 2.5 0 0 1 4 13.5v-8Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
              <div className="min-w-0 space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <label className="rounded-lg px-3 py-1.5 text-xs font-medium cursor-pointer"
                    style={{ background: "var(--accent)", color: "#fff", opacity: logoBusy ? 0.6 : 1 }}>
                    {logoBusy ? "Đang tải…" : app?.logo_url ? "Đổi logo" : "Tải logo lên"}
                    <input type="file" className="hidden" disabled={logoBusy} data-testid="logo-input"
                      accept="image/png,image/jpeg,image/webp,image/gif,image/svg+xml,image/x-icon,image/vnd.microsoft.icon,.ico,.svg"
                      onChange={(e) => { const f = e.target.files?.[0] || null; e.currentTarget.value = ""; handleLogoFile(f); }} />
                  </label>
                  {app?.logo_url && (
                    <button type="button" onClick={handleLogoRemove} disabled={logoBusy}
                      className="rounded-lg px-3 py-1.5 text-xs font-medium" style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                      Xoá logo
                    </button>
                  )}
                </div>
                <p className="text-[11px]" style={{ color: logoError ? "#ef4444" : "var(--muted)" }}>
                  {logoError || "PNG, JPG, WebP, GIF, ICO hoặc SVG, tối đa 1 MB, nên dùng ảnh vuông ≥ 128 px. Hiển thị trên bong bóng chat, khung chat, trang khách hàng và cổng cán bộ. Lưu ngay khi chọn."}
                </p>
              </div>
            </div>
          </Field>

          {audience === "staff" && (
            <Field label="Phạm vi hiển thị trên cổng cán bộ">
              <div className="grid grid-cols-2 gap-2">
                {([
                  { v: "unit", label: "Chỉ đơn vị này", hint: "Chỉ cán bộ thuộc đơn vị sở hữu trợ lý nhìn thấy và hỏi được" },
                  { v: "bank", label: "Toàn ngân hàng", hint: "Mọi cán bộ ở tất cả đơn vị đều thấy và dùng được trợ lý này" },
                ] as { v: AppShareScope; label: string; hint: string }[]).map((o) => {
                  const active = shareScope === o.v;
                  return (
                    <button key={o.v} type="button" onClick={() => isOwner && setShareScope(o.v)} disabled={!isOwner} data-testid={`share-${o.v}`}
                      className="rounded-lg px-3 py-2.5 text-left text-xs transition-all"
                      style={{ background: active ? "var(--accent-glow)" : "var(--background)", border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                        color: active ? "var(--accent-hover)" : "var(--foreground)", opacity: isOwner ? 1 : 0.6, cursor: isOwner ? "pointer" : "not-allowed" }}>
                      <span className="block font-semibold">{o.label}</span>
                      <span className="block mt-0.5" style={{ color: "var(--muted)" }}>{o.hint}</span>
                    </button>
                  );
                })}
              </div>
              <p className="text-[11px] mt-1.5" style={{ color: "var(--muted)" }}>
                {isOwner ? "Mặc định trợ lý chỉ hiện với cán bộ của đơn vị này. Mở cho toàn ngân hàng khi nội dung áp dụng chung (vd. tuân thủ)." : "Chỉ chủ đơn vị (owner) mới được đổi phạm vi hiển thị."}
              </p>
            </Field>
          )}

          {audience === "staff" && (
            <Field label="Browser extension (bong bóng trên trình duyệt của cán bộ)">
              <div className="flex items-center gap-3">
                <Toggle on={extensionEnabled} onChange={setExtensionEnabled} />
                <span className="text-sm" style={{ color: extensionEnabled ? "#22c55e" : "var(--muted)" }} data-testid="extension-state">
                  {extensionEnabled ? "Đang bật — cán bộ đã cài extension chọn được trợ lý này trong bong bóng" : "Tắt — không xuất hiện trong bong bóng"}
                </span>
              </div>
              {extensionEnabled && (
                <div className="mt-2">
                  <textarea value={extensionHostsText} onChange={(e) => setExtensionHostsText(e.target.value)} rows={3}
                    placeholder={"bpm.msb.local\n*.ttqt.msb.local\nlocalhost:8092"}
                    className="w-full text-xs font-mono rounded-lg px-3 py-2 outline-none" style={fieldStyle} data-testid="extension-hosts" />
                  <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
                    Mỗi dòng một tên miền nội bộ. Vào trang khớp tên miền, bong bóng mở sẵn trợ lý này; để trống thì trợ lý chỉ nằm trong danh sách chọn.
                    Dùng <code>*.</code> cho tên miền con. Cán bộ vẫn phải đăng nhập và trợ lý phải được công bố.
                  </p>
                </div>
              )}
            </Field>
          )}

          <Field label="Công bố">
            <div className="flex items-center gap-3">
              <Toggle on={isPublished} onChange={setIsPublished} />
              <span className="text-sm" style={{ color: isPublished ? "#22c55e" : "var(--muted)" }}>
                {isPublished
                  ? (audience === "customer" ? "Đã công bố — khách hàng truy cập qua link bên dưới" : "Đã công bố — hiển thị trên cổng Trợ lý cán bộ")
                  : "Chưa công bố — chỉ admin thấy"}
              </span>
            </div>
          </Field>

          {app.audience === "customer" && (
            <Field label="Link cho khách hàng">
              <div className="flex gap-2">
                <div className="flex-1 text-xs font-mono px-3 py-2 rounded-lg truncate" style={fieldStyle}>{customerLink(app)}</div>
                <button onClick={() => copy("link")} className="rounded-lg px-3 py-2 text-xs font-medium flex-shrink-0"
                  style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>
                  {copied === "link" ? "✓ Đã sao chép" : "Sao chép"}
                </button>
                <a href={customerLink(app)} target="_blank" rel="noreferrer" className="rounded-lg px-3 py-2 text-xs font-medium flex-shrink-0"
                  style={{ background: "var(--card)", color: "var(--foreground)", border: "1px solid var(--border)" }}>Mở ↗</a>
              </div>
              {!app.is_published && <p className="text-[11px] mt-1" style={{ color: "#f59e0b" }}>Link chỉ hoạt động khi trợ lý đã công bố.</p>}
            </Field>
          )}

          <Field label="API key (publishable — dùng cho link khách hàng và bản nhúng)">
            <div className="flex gap-2">
              <div className="flex-1 text-xs font-mono px-3 py-2 rounded-lg truncate" style={fieldStyle}>{app.api_key}</div>
              <button onClick={() => copy("key")} className="rounded-lg px-3 py-2 text-xs font-medium flex-shrink-0"
                style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>
                {copied === "key" ? "✓ Đã sao chép" : "Sao chép"}
              </button>
              <button onClick={handleRegenKey} className="rounded-lg px-3 py-2 text-xs font-medium flex-shrink-0"
                style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444" }}>
                Tạo lại
              </button>
            </div>
          </Field>

          {saveError && (
            <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>{saveError}</div>
          )}

          <SaveButton saving={saving} saved={saved} disabled={!!datasetBlocked} onClick={handleSave} />
        </div>
      )}

      {tab === "tools" && (() => {
        const isCustomerApp = audience === "customer";
        // customers: only tools opened to the customer channel and not approval-gated (nobody to approve)
        const usable = (t: ToolResponse) => !isCustomerApp || (t.allow_customer && !t.requires_approval);
        // ticking a tool while the switch is off binds a tool the assistant never calls, so turn
        // the switch on with the first tool; it stays visible and can be turned back off
        const toggleTool = (id: string) => setToolIds((ids) => {
          const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
          if (next.length > 0) setAgentEnabled(true);
          return next;
        });
        return (
          <div className="space-y-5">
            <div className="rounded-xl px-4 py-3 text-xs" style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--muted)" }}>
              Khi bật, trợ lý được tự quyết định gọi công cụ đã chọn để lấy dữ liệu thật hoặc tính toán, rồi trả lời kèm trích dẫn tài liệu như bình thường.
              Công cụ đánh dấu <strong>cần duyệt</strong> sẽ dừng lại hiện thẻ xác nhận cho cán bộ trước khi chạy.
              {isCustomerApp && " Trợ lý khách hàng chỉ dùng được công cụ đã mở cho kênh khách hàng và không cần duyệt."}
            </div>

            <Field label="Cho phép trợ lý gọi công cụ">
              <div className="flex items-center gap-3">
                <Toggle on={agentEnabled} onChange={setAgentEnabled} />
                <span className="text-sm" style={{ color: agentEnabled ? "#22c55e" : "var(--muted)" }} data-testid="agent-state">
                  {agentEnabled ? `Đang bật · ${toolIds.length} công cụ` : "Tắt — trả lời chỉ từ tài liệu / luồng xử lý"}
                </span>
              </div>
              {!agentEnabled && toolIds.length > 0 && (
                <p className="text-[11px] mt-1.5" style={{ color: "#ef4444" }} data-testid="agent-off-warning">
                  Đã chọn {toolIds.length} công cụ nhưng công tắc đang tắt: trợ lý sẽ không gọi công cụ nào.
                  Bật lên rồi lưu thì trợ lý mới dùng được.
                </p>
              )}
              {agentEnabled && workflowId && (
                <p className="text-[11px] mt-1.5" style={{ color: "#f59e0b" }}>Khi có công cụ, trợ lý chạy chế độ agent thay cho luồng xử lý đang gắn.</p>
              )}
            </Field>

            <Field label="Công cụ được dùng">
              {tools.length === 0 ? (
                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  Đơn vị chưa có công cụ nào. Tạo ở mục <a href="/tools" className="underline" style={{ color: "var(--accent)" }}>Công cụ</a>.
                </p>
              ) : (
                <div className="space-y-1.5" data-testid="app-tool-list">
                  {tools.map((t) => {
                    const checked = toolIds.includes(t.id);
                    const allowed = usable(t);
                    return (
                      <label key={t.id} className="flex items-start gap-3 rounded-lg px-3 py-2.5 text-xs"
                        style={{ background: checked ? "var(--accent-glow)" : "var(--background)", border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
                          opacity: allowed || checked ? 1 : 0.5, cursor: allowed ? "pointer" : "not-allowed" }}>
                        <input type="checkbox" checked={checked} disabled={!allowed && !checked} onChange={() => toggleTool(t.id)} className="mt-0.5" data-testid={`bind-${t.slug}`} />
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-1.5">
                            <span className="font-semibold" style={{ color: "var(--foreground)" }}>{t.name}</span>
                            <span className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{t.slug}</span>
                            <span className="rounded-full px-1.5 text-[10px]" style={{ background: "var(--card)", color: "var(--muted)" }}>{KIND_LABEL[t.kind]}</span>
                            {t.requires_approval && <span className="rounded-full px-1.5 text-[10px] font-semibold" style={{ background: "rgba(245,158,11,0.14)", color: "#b45309" }}>Cần duyệt</span>}
                            {t.share_scope === "bank" && !t.own_unit && <span className="rounded-full px-1.5 text-[10px] font-semibold" style={{ background: "rgba(59,130,246,0.12)", color: "#2563eb" }}>Dùng chung</span>}
                          </span>
                          <span className="block mt-0.5 line-clamp-2" style={{ color: "var(--muted)" }}>{t.description}</span>
                          {!allowed && <span className="block mt-0.5" style={{ color: "#ef4444" }}>Chưa mở cho kênh khách hàng hoặc cần duyệt — không gắn được.</span>}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </Field>

            {saveError && <p className="text-xs" style={{ color: "#ef4444" }}>{saveError}</p>}
            <SaveButton saving={saving} saved={saved} disabled={!!datasetBlocked} onClick={handleSave} />
          </div>
        );
      })()}

      {tab === "skills" && (() => {
        const isCustomerApp = audience === "customer";
        const usable = (k: Skill) => k.status === "published" && (!isCustomerApp || k.allow_customer);
        const toggle = (id: string) => setSkillIds((ids) =>
          ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);
        return (
          <div className="space-y-5">
            <div className="rounded-xl px-4 py-3 text-xs"
                 style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--muted)" }}>
              Kỹ năng là bí kíp nghiệp vụ trợ lý nạp <strong>khi cần</strong>. Trợ lý luôn thấy tên và
              mô tả của mọi kỹ năng đã gắn, nhưng chỉ đọc toàn văn kỹ năng khớp câu hỏi, nên gắn thêm
              kỹ năng không làm nặng những câu hỏi không liên quan.
              {isCustomerApp && " Trợ lý khách hàng chỉ dùng được kỹ năng đã mở cho kênh khách hàng."}
            </div>

            <Field label="Kỹ năng được dùng">
              {skills.length === 0 ? (
                <p className="text-xs" style={{ color: "var(--muted)" }}>
                  Đơn vị chưa có kỹ năng nào. Soạn ở mục{" "}
                  <a href="/skills" className="underline" style={{ color: "var(--accent)" }}>Kỹ năng</a>.
                </p>
              ) : (
                <div className="space-y-1.5" data-testid="app-skill-list">
                  {skills.map((k) => {
                    const checked = skillIds.includes(k.id);
                    const allowed = usable(k);
                    return (
                      <label key={k.id} className="flex items-start gap-3 rounded-lg px-3 py-2.5 text-xs"
                        style={{
                          background: checked ? "var(--accent-glow)" : "var(--background)",
                          border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
                          opacity: allowed || checked ? 1 : 0.5,
                          cursor: allowed ? "pointer" : "not-allowed",
                        }}>
                        <input type="checkbox" checked={checked} disabled={!allowed && !checked}
                               onChange={() => toggle(k.id)} className="mt-0.5"
                               data-testid={`bind-skill-${k.slug}`} />
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-1.5">
                            <span className="font-semibold" style={{ color: "var(--foreground)" }}>{k.name}</span>
                            <span className="font-mono text-[10px]" style={{ color: "var(--muted)" }}>{k.slug}</span>
                            <span className="rounded-full px-1.5 text-[10px]"
                                  style={{ background: "var(--card)", color: "var(--muted)" }}>{k.version}</span>
                            {k.status !== "published" && (
                              <span className="rounded-full px-1.5 text-[10px] font-semibold"
                                    style={{ background: "rgba(100,116,139,0.14)", color: "#64748b" }}>Chưa công bố</span>
                            )}
                            {k.share_scope === "bank" && !k.own_unit && (
                              <span className="rounded-full px-1.5 text-[10px] font-semibold"
                                    style={{ background: "rgba(59,130,246,0.12)", color: "#2563eb" }}>Dùng chung</span>
                            )}
                          </span>
                          <span className="mt-0.5 block" style={{ color: "var(--muted)" }}>{k.description}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </Field>

            <Field label="Bộ nhớ cá nhân của cán bộ">
              <div className="flex items-center gap-3">
                <Toggle on={memoryEnabled} onChange={setMemoryEnabled} />
                <span className="text-sm" style={{ color: memoryEnabled ? "#22c55e" : "var(--muted)" }}
                      data-testid="memory-state">
                  {memoryEnabled ? "Đang bật — trợ lý nhớ cách làm việc của từng cán bộ"
                                 : "Tắt — trợ lý không đọc và không ghi bộ nhớ"}
                </span>
              </div>
              <p className="mt-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
                Bộ nhớ thuộc về cán bộ chứ không thuộc về trợ lý, và chỉ nhớ cách họ làm việc: muốn
                câu trả lời ngắn hay dài, phụ trách mảng nào, đang theo hồ sơ nào. Nó{" "}
                <strong>không bao giờ</strong> nhớ thông tin khách hàng hay nội dung quy định. Cán bộ
                tự xem và xoá tại &ldquo;Trợ lý nhớ gì về tôi&rdquo; trong cổng cán bộ.
                {audience === "customer" && " Kênh khách hàng không có bộ nhớ dài hạn."}
              </p>
            </Field>
          </div>
        );
      })()}

      {tab === "embed" && (
        <div className="space-y-5">
          <div className="rounded-xl px-4 py-3 text-xs" style={{ background: "var(--card)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            Bong bóng chat chạy trong <strong>iframe từ hệ thống này</strong>, website đối tác chỉ dán một dòng script. Trình duyệt chỉ cho phép nhúng trên các website trong danh sách bên dưới (CSP <code>frame-ancestors</code>); mọi lượt hỏi được ghi vào Nhật ký truy vấn kèm website nguồn.
            {app.audience === "staff" && <> Với trợ lý cán bộ, người dùng <strong>đăng nhập tài khoản cán bộ ngay trong khung chat</strong>; key công khai chỉ mở phần cấu hình giao diện.</>}
          </div>

          <Field label="Bật nhúng">
            <div className="flex items-center gap-3">
              <Toggle on={embedEnabled} onChange={setEmbedEnabled} disabled={origins.length === 0} />
              <span className="text-sm" style={{ color: embedEnabled ? "#22c55e" : "var(--muted)" }}>
                {origins.length === 0 ? "Thêm ít nhất một website được phép trước khi bật" : embedEnabled ? "Đang bật — chỉ các website bên dưới nhúng được" : "Đang tắt"}
              </span>
            </div>
          </Field>

          <Field label={`Website được phép nhúng (origin) — ${origins.length}/20`}>
            <div className="space-y-2">
              {origins.map((o) => (
                <div key={o} className="flex items-center gap-2">
                  <code className="flex-1 text-xs px-3 py-2 rounded-lg" style={fieldStyle}>{o}</code>
                  <button onClick={() => setOrigins((list) => list.filter((x) => x !== o))} className="rounded-lg px-2 py-2 text-xs" style={{ color: "#ef4444", border: "1px solid var(--border)" }} aria-label={`Xoá ${o}`}>Xoá</button>
                </div>
              ))}
              <div className="flex gap-2">
                <input value={newOrigin} onChange={(e) => { setNewOrigin(e.target.value); setOriginError(null); }}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addOrigin(); } }}
                  placeholder="https://www.msb.com.vn hoặc http://localhost:8090"
                  className="flex-1 text-sm rounded-lg px-3 py-2 outline-none font-mono" style={fieldStyle} />
                <button onClick={addOrigin} className="rounded-lg px-3 py-2 text-xs font-medium" style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>Thêm</button>
              </div>
              {originError && <p className="text-[11px]" style={{ color: "#ef4444" }}>{originError}</p>}
              <p className="text-[11px]" style={{ color: "var(--muted)" }}>Origin = scheme + tên miền (+ cổng), không có đường dẫn. Mỗi tên miền con là một origin riêng.</p>
            </div>
          </Field>

          <Field label="Giao diện bong bóng">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Tiêu đề (mặc định: tên trợ lý)</label>
                <input value={widget.title || ""} onChange={(e) => setWidget({ ...widget, title: e.target.value })} className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
              </div>
              <div>
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Dòng phụ</label>
                <input value={widget.subtitle || ""} onChange={(e) => setWidget({ ...widget, subtitle: e.target.value })} placeholder="Trả lời từ tài liệu chính thức" className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
              </div>
              <div className="sm:col-span-2">
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Lời chào (hiện trong khung chat và bong bóng gợi mở)</label>
                <textarea value={widget.greeting || ""} onChange={(e) => setWidget({ ...widget, greeting: e.target.value })} rows={2} placeholder="Xin chào! Tôi có thể giúp gì cho bạn?" className="w-full text-sm rounded-lg px-3 py-2 outline-none resize-y" style={fieldStyle} />
              </div>
              <div>
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Màu chủ đạo</label>
                <div className="flex gap-2 items-center">
                  <input type="color" value={widget.primary_color || "#ee6d1f"} onChange={(e) => setWidget({ ...widget, primary_color: e.target.value })} className="h-9 w-12 rounded-lg" style={{ border: "1px solid var(--border)", background: "transparent" }} />
                  <input value={widget.primary_color || "#ee6d1f"} onChange={(e) => setWidget({ ...widget, primary_color: e.target.value })} className="flex-1 text-sm rounded-lg px-3 py-2 outline-none font-mono" style={fieldStyle} />
                </div>
              </div>
              <div>
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Vị trí · Giao diện</label>
                <div className="flex gap-2">
                  <select value={widget.position || "right"} onChange={(e) => setWidget({ ...widget, position: e.target.value as "right" | "left" })} className="flex-1 text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
                    <option value="right">Góc phải</option><option value="left">Góc trái</option>
                  </select>
                  <select value={widget.theme || "light"} onChange={(e) => setWidget({ ...widget, theme: e.target.value as "light" | "dark" | "auto" })} className="flex-1 text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
                    <option value="light">Sáng</option><option value="dark">Tối</option><option value="auto">Theo hệ thống</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Nhãn nút bong bóng</label>
                <input value={widget.launcher_text || ""} onChange={(e) => setWidget({ ...widget, launcher_text: e.target.value })} placeholder="Hỗ trợ trực tuyến" className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
              </div>
              <div className="flex items-center gap-3 pt-5">
                <Toggle on={widget.show_powered_by !== false} onChange={(v) => setWidget({ ...widget, show_powered_by: v })} />
                <span className="text-xs" style={{ color: "var(--muted)" }}>Hiện "Powered by"</span>
              </div>
              <div className="sm:col-span-2">
                <label className="text-[10px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Gợi ý câu hỏi (mỗi dòng một câu, tối đa 4)</label>
                <textarea value={suggestionsText} onChange={(e) => setSuggestionsText(e.target.value)} rows={3} className="w-full text-sm rounded-lg px-3 py-2 outline-none resize-y" style={fieldStyle} />
              </div>
            </div>
          </Field>

          {saveError && (
            <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>{saveError}</div>
          )}
          <div className="flex items-center gap-3">
            <SaveButton saving={saving} saved={saved} onClick={handleSave} />
            {embedDirty && <span className="text-xs" style={{ color: "#f59e0b" }}>Có thay đổi chưa lưu — snippet và preview dùng cấu hình đã lưu.</span>}
          </div>

          <Field label="Snippet — dán trước </body> của website được phép">
            <div className="flex gap-2">
              <pre className="flex-1 text-[11px] font-mono px-3 py-2 rounded-lg overflow-x-auto whitespace-pre-wrap break-all" style={fieldStyle}>{embedSnippet(app)}</pre>
              <button onClick={() => copy("snippet")} className="rounded-lg px-3 py-2 text-xs font-medium flex-shrink-0 self-start"
                style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>
                {copied === "snippet" ? "✓ Đã sao chép" : "Sao chép"}
              </button>
            </div>
            <p className="text-[11px] mt-1" style={{ color: "var(--muted)" }}>
              Key trong snippet là <strong>publishable key</strong>: chỉ mở được trợ lý này qua kênh công khai/nhúng, không truy cập được API quản trị. Nếu lộ hoặc muốn thu hồi, bấm "Tạo lại" ở tab Cấu hình — mọi bản nhúng cũ ngừng hoạt động ngay.
              {!app.is_published && <span style={{ color: "#f59e0b" }}> Trợ lý chưa công bố nên bản nhúng chưa hoạt động.</span>}
              {!app.embed_enabled && app.is_published && <span style={{ color: "#f59e0b" }}> Chưa bật nhúng — website đối tác sẽ bị chặn.</span>}
            </p>
          </Field>

          <Field label="Xem trước (đúng giao diện khung chat như trên website)">
            <div className="flex items-center gap-2 mb-2">
              <button onClick={() => setPreviewNonce((n) => n + 1)} className="rounded-lg px-3 py-1.5 text-xs font-medium" style={{ background: "var(--card)", color: "var(--foreground)", border: "1px solid var(--border)" }}>↻ Tải lại preview</button>
              <span className="text-[11px]" style={{ color: "var(--muted)" }}>Preview dùng cấu hình đã lưu.</span>
            </div>
            <div className="rounded-2xl overflow-hidden" style={{ width: 380, height: 600, maxWidth: "100%", border: "1px solid var(--border)", boxShadow: "0 16px 48px rgba(0,0,0,0.18)" }}>
              <iframe key={previewNonce} src={embedPreviewUrl(app)} title="Preview khung chat" style={{ width: "100%", height: "100%", border: 0 }}
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />
            </div>
          </Field>
        </div>
      )}

      {tab === "runs" && (
        <div>
          {runs.length === 0 ? (
            <div className="text-center py-12">
              <p className="text-sm" style={{ color: "var(--muted)" }}>Chưa có lượt chạy. Hỏi đáp với trợ lý này để sinh nhật ký.</p>
            </div>
          ) : (
            <div className="rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: "var(--card)" }}>
                    {["Trạng thái", "Bắt đầu", "Độ trễ", ""].map((h) => (
                      <th key={h} className="text-left px-4 py-2.5 font-semibold" style={{ color: "var(--muted)" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id} className="transition-colors" style={{ borderTop: "1px solid var(--border)" }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = "var(--card)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>
                      <td className="px-4 py-2.5">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold"
                          style={{
                            background: run.status === "completed" ? "rgba(34,197,94,0.12)" : run.status === "failed" ? "rgba(239,68,68,0.12)" : "rgba(245,158,11,0.12)",
                            color: run.status === "completed" ? "#22c55e" : run.status === "failed" ? "#ef4444" : "#f59e0b",
                          }}>
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5" style={{ color: "var(--foreground)" }}>{new Date(run.started_at).toLocaleString()}</td>
                      <td className="px-4 py-2.5" style={{ color: "var(--foreground)" }}>{run.latency_ms != null ? `${run.latency_ms}ms` : "—"}</td>
                      <td className="px-4 py-2.5">
                        <button onClick={() => viewSteps(run.id)} className="text-xs font-medium" style={{ color: "var(--accent)" }}>Xem các bước</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {selectedRun && (
            <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
              onClick={() => setSelectedRun(null)}>
              <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-6"
                style={{ background: "var(--card)", border: "1px solid var(--border)", width: 600, maxHeight: "80vh", overflow: "auto" }}>
                <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--foreground)" }}>🔍 Các bước xử lý ({steps.length})</h3>
                {steps.length === 0 ? (
                  <p className="text-sm" style={{ color: "var(--muted)" }}>Không có bước nào được ghi.</p>
                ) : (
                  <div className="space-y-2">
                    {steps.map((step, i) => (
                      <div key={step.id} className="rounded-lg p-3" style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-bold rounded px-1.5 py-0.5" style={{ background: "var(--accent-glow)", color: "var(--accent)" }}>{i + 1}</span>
                            <span className="text-xs font-semibold" style={{ color: "var(--foreground)" }}>{step.node_type}</span>
                            <span className="text-[10px]" style={{ color: "var(--muted)" }}>({step.node_id})</span>
                          </div>
                          <span className="text-xs font-mono" style={{ color: step.duration_ms != null && step.duration_ms > 1000 ? "#f59e0b" : "#22c55e" }}>
                            {step.duration_ms != null ? `${step.duration_ms}ms` : "..."}
                          </span>
                        </div>
                        {step.output_json && (
                          <pre className="text-[10px] mt-1 font-mono overflow-x-auto whitespace-pre-wrap" style={{ color: "var(--muted)" }}>
                            {JSON.stringify(step.output_json, null, 2).slice(0, 400)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-semibold block mb-1.5" style={{ color: "var(--muted)" }}>{label}</label>
      {children}
    </div>
  );
}

function SaveButton({ saving, saved, disabled, onClick }: { saving: boolean; saved: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} disabled={saving || !!disabled}
      className="rounded-lg px-5 py-2.5 text-sm font-medium"
      style={{ background: disabled ? "var(--muted)" : "var(--accent)", color: "#fff", cursor: disabled ? "not-allowed" : "pointer" }}>
      {saving ? "..." : saved ? "✓ Đã lưu" : "Lưu thay đổi"}
    </button>
  );
}
