"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import {
  CRON_PRESETS, POSITIONS, ScheduleInput, ScheduleResponse,
  createSchedule, deleteSchedule, listSchedules, previewCron, runScheduleNow, schedulerStatus, updateSchedule,
} from "@/lib/api/schedules";
import { WorkflowResponse, InputField, listWorkflows, inputFieldsOf } from "@/lib/api/workflows";
import { ArtifactResponse, downloadArtifact, formatBytes, listArtifacts } from "@/lib/api/artifacts";

const fieldStyle = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

const fmtTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";

const STATUS: Record<string, { label: string; color: string }> = {
  completed: { label: "✓ Hoàn thành", color: "#22c55e" },
  failed: { label: "✕ Lỗi", color: "#ef4444" },
  running: { label: "● Đang chạy", color: "#f59e0b" },
  queued: { label: "⏳ Đang chờ", color: "#f59e0b" },
};

export default function SchedulesPage() {
  const { user } = useAuth();
  const [schedules, setSchedules] = useState<ScheduleResponse[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactResponse[]>([]);
  const [ticker, setTicker] = useState<{ running: boolean; last_heartbeat: string | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ScheduleResponse | "new" | null>(null);

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, w, a, st] = await Promise.all([
        listSchedules(), listWorkflows(), listArtifacts({ days: 30 }), schedulerStatus().catch(() => null),
      ]);
      setSchedules(s); setWorkflows(w); setArtifacts(a); setTicker(st);
    } catch (e: any) { setError(e.message || "Không tải được lịch chạy"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(() => { listSchedules().then(setSchedules).catch(() => {}); listArtifacts({ days: 30 }).then(setArtifacts).catch(() => {}); }, 10000);
    return () => clearInterval(t);
  }, []);

  const reportWorkflows = useMemo(() => workflows.filter((w) => w.type === "report"), [workflows]);
  const filesOf = (s: ScheduleResponse) => artifacts.filter((a) => a.schedule_id === s.id);

  const toggle = async (s: ScheduleResponse) => {
    try {
      const updated = await updateSchedule(s.id, { enabled: !s.enabled });
      setSchedules((prev) => prev.map((x) => (x.id === s.id ? updated : x)));
    } catch (e: any) { setError(e.message || "Không đổi được trạng thái"); load(); }
  };

  const runNow = async (s: ScheduleResponse) => {
    try { await runScheduleNow(s.id); setTimeout(load, 1500); }
    catch (e: any) { setError(e.message || "Không chạy được"); }
  };

  const remove = async (s: ScheduleResponse) => {
    if (!confirm(`Xoá lịch "${s.name}"? Các báo cáo đã tạo vẫn được giữ.`)) return;
    try { await deleteSchedule(s.id); setSchedules((prev) => prev.filter((x) => x.id !== s.id)); }
    catch (e: any) { setError(e.message || "Không xoá được"); }
  };

  if (!isAdmin) return <div className="text-center py-20 text-sm" style={{ color: "var(--muted)" }}>Không có quyền truy cập</div>;

  return (
    <div>
      <div className="page-header flex items-center justify-between mb-5">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Lịch chạy</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            Chạy luồng báo cáo theo giờ cố định. Báo cáo chạy xong nằm ở đây và trong mục “Báo cáo” của cán bộ thuộc đơn vị.
          </p>
        </div>
        <button onClick={() => setEditing("new")} disabled={reportWorkflows.length === 0}
          className="shrink-0 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-medium"
          style={{ background: reportWorkflows.length ? "var(--accent)" : "var(--border)", color: "#fff" }}
          data-testid="new-schedule">
          + Lịch mới
        </button>
      </div>

      {ticker && !ticker.running && (
        <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "rgba(245,158,11,0.12)", color: "#b45309" }}>
          Bộ lập lịch chưa chạy (dịch vụ <code>scheduler</code>). Lịch sẽ không tự kích hoạt cho tới khi dịch vụ này bật.
        </div>
      )}
      {reportWorkflows.length === 0 && (
        <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "var(--card)", color: "var(--muted)", border: "1px solid var(--border)" }}>
          Đơn vị chưa có luồng báo cáo nào. Tạo ở mục <Link href="/workflows" className="underline" style={{ color: "var(--accent)" }}>Luồng xử lý</Link> → “Luồng báo cáo”.
        </div>
      )}
      {error && <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>{error}</div>}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : schedules.length === 0 ? (
        <div className="text-center py-16 rounded-xl" style={{ border: "1px dashed var(--border)", background: "var(--card)" }}>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Chưa có lịch chạy nào.</p>
        </div>
      ) : (
        <div className="space-y-3" data-testid="schedule-list">
          {schedules.map((s) => {
            const files = filesOf(s);
            const st = s.last_status ? STATUS[s.last_status] : null;
            return (
              <div key={s.id} className="rounded-xl p-4" style={{ background: "var(--card)", border: "1px solid var(--border)" }}
                data-testid={`schedule-${s.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm" style={{ color: "var(--foreground)" }}>{s.name}</span>
                      <span className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                        style={{ background: s.enabled ? "rgba(34,197,94,0.12)" : "rgba(107,114,128,0.14)", color: s.enabled ? "#22c55e" : "var(--muted)" }}>
                        {s.enabled ? "ĐANG BẬT" : "ĐÃ TẮT"}
                      </span>
                      {st && <span className="text-[11px]" style={{ color: st.color }}>{st.label}</span>}
                    </div>
                    <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
                      🕒 {s.cron_label} · 📄 {s.workflow_name || "(luồng đã xoá)"} ·{" "}
                      {s.deliver_positions.length ? `gửi ${s.deliver_positions.join(", ")}` : "gửi mọi cán bộ trong đơn vị"}
                    </p>
                    <p className="text-[11px] mt-0.5" style={{ color: "var(--muted)" }}>
                      Lần kế: <strong style={{ color: "var(--foreground)" }}>{s.enabled ? fmtTime(s.next_run_at) : "—"}</strong>
                      {" · "}Lần cuối: {fmtTime(s.last_enqueued_at)}
                      {Object.keys(s.inputs || {}).length > 0 && ` · tham số: ${Object.entries(s.inputs).map(([k, v]) => `${k}=${v}`).join(", ")}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button onClick={() => runNow(s)} className="text-xs rounded-lg px-2.5 py-1.5"
                      style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}
                      data-testid="run-now">Chạy ngay</button>
                    <button onClick={() => toggle(s)} className="text-xs rounded-lg px-2.5 py-1.5"
                      style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}
                      data-testid="toggle-schedule">{s.enabled ? "Tắt" : "Bật"}</button>
                    <button onClick={() => setEditing(s)} className="text-xs rounded-lg px-2.5 py-1.5"
                      style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>Sửa</button>
                    <button onClick={() => remove(s)} className="text-xs rounded-lg px-2.5 py-1.5"
                      style={{ background: "rgba(239,68,68,0.08)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>Xoá</button>
                  </div>
                </div>
                {files.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {files.slice(0, 6).map((a) => (
                      <button key={a.id} onClick={() => downloadArtifact(a)} data-testid="schedule-artifact"
                        className="text-[11px] rounded-lg px-2 py-1"
                        style={{ background: "rgba(132,204,22,0.10)", color: "#84cc16" }}>
                        📄 {a.title || a.filename} · {formatBytes(a.size)} · {fmtTime(a.created_at)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {editing && (
        <ScheduleEditor
          schedule={editing === "new" ? null : editing}
          workflows={reportWorkflows}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

function ScheduleEditor({ schedule, workflows, onClose, onSaved }: {
  schedule: ScheduleResponse | null;
  workflows: WorkflowResponse[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(schedule?.name || "");
  const [workflowId, setWorkflowId] = useState(schedule?.workflow_id || workflows[0]?.id || "");
  const [preset, setPreset] = useState(1);            // ngày làm việc
  const [atTime, setAtTime] = useState("07:30");
  const [cron, setCron] = useState(schedule?.cron || "30 7 * * 1-5");
  const [positions, setPositions] = useState<string[]>(schedule?.deliver_positions || []);
  const [inputs, setInputs] = useState<Record<string, any>>(schedule?.inputs || {});
  const [retention, setRetention] = useState(schedule?.retention_days ?? 30);
  const [nextRuns, setNextRuns] = useState<string[]>([]);
  const [cronLabel, setCronLabel] = useState(schedule?.cron_label || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wf = workflows.find((w) => w.id === workflowId);
  const fields: InputField[] = useMemo(() => inputFieldsOf(wf?.graph_json), [wf]);

  useEffect(() => {
    if (!schedule && !name && wf) setName(`Lịch: ${wf.name}`);
  }, [wf, schedule, name]);

  useEffect(() => {
    let alive = true;
    previewCron(cron).then((p) => { if (alive) { setNextRuns(p.next_runs); setCronLabel(p.cron_label); setError(null); } })
      .catch((e) => { if (alive) { setNextRuns([]); setError(e.message || "Cron không hợp lệ"); } });
    return () => { alive = false; };
  }, [cron]);

  const applyPreset = (index: number, time: string) => {
    setPreset(index); setAtTime(time);
    setCron(CRON_PRESETS[index].cron(time));
  };

  const save = async () => {
    setSaving(true); setError(null);
    try {
      const payload: ScheduleInput = {
        workflow_id: workflowId, name: name.trim() || wf?.name || "Lịch báo cáo", cron,
        inputs, deliver_positions: positions, retention_days: retention,
      };
      if (schedule) await updateSchedule(schedule.id, payload);
      else await createSchedule(payload);
      onSaved();
    } catch (e: any) { setError(e.message || "Lưu thất bại"); }
    finally { setSaving(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(3px)" }}
      onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-6 w-full"
        style={{ background: "var(--card)", border: "1px solid var(--border)", maxWidth: 560, maxHeight: "86vh", overflowY: "auto" }}
        data-testid="schedule-editor">
        <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          {schedule ? "Sửa lịch chạy" : "Lịch chạy mới"}
        </h3>

        <div className="space-y-3">
          <L label="Luồng báo cáo">
            <select value={workflowId} onChange={(e) => setWorkflowId(e.target.value)} disabled={!!schedule}
              className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} data-testid="schedule-workflow">
              {workflows.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </L>
          <L label="Tên lịch">
            <input value={name} onChange={(e) => setName(e.target.value)}
              className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} data-testid="schedule-name" />
          </L>

          <L label="Chu kỳ">
            <div className="flex gap-2">
              <select value={preset} onChange={(e) => applyPreset(Number(e.target.value), atTime)}
                className="flex-1 text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} data-testid="schedule-preset">
                {CRON_PRESETS.map((p, i) => <option key={p.label} value={i}>{p.label}</option>)}
              </select>
              <input type="time" value={atTime} onChange={(e) => applyPreset(preset, e.target.value)}
                className="text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} data-testid="schedule-time" />
            </div>
            <input value={cron} onChange={(e) => setCron(e.target.value)}
              className="w-full text-xs rounded-lg px-3 py-2 outline-none font-mono mt-2" style={fieldStyle}
              data-testid="schedule-cron" />
            <p className="text-[11px] mt-1" style={{ color: error ? "#ef4444" : "var(--muted)" }}>
              {error || `${cronLabel} (giờ Việt Nam) · lần kế: ${nextRuns.slice(0, 3).map((d) => fmtTime(d)).join(" · ") || "—"}`}
            </p>
          </L>

          {fields.length > 0 && (
            <L label="Tham số báo cáo">
              <div className="space-y-2" data-testid="schedule-inputs">
                {fields.map((f) => (
                  <div key={f.name}>
                    <label className="text-[11px]" style={{ color: "var(--muted)" }}>{f.label || f.name}</label>
                    {f.type === "boolean" ? (
                      <label className="flex items-center gap-2 text-xs" style={{ color: "var(--foreground)" }}>
                        <input type="checkbox" checked={!!inputs[f.name]}
                          onChange={(e) => setInputs((v) => ({ ...v, [f.name]: e.target.checked }))} />
                        {f.description || "Có"}
                      </label>
                    ) : f.type === "select" ? (
                      <select value={inputs[f.name] ?? ""} onChange={(e) => setInputs((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle}>
                        <option value="">—</option>
                        {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                        value={inputs[f.name] ?? ""} placeholder={f.description || ""}
                        onChange={(e) => setInputs((v) => ({ ...v, [f.name]: e.target.value }))}
                        className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
                    )}
                  </div>
                ))}
              </div>
            </L>
          )}

          <L label="Gửi cho chức danh (bỏ trống = mọi cán bộ trong đơn vị)">
            <div className="flex flex-wrap gap-1.5" data-testid="schedule-positions">
              {POSITIONS.map((p) => {
                const on = positions.includes(p);
                return (
                  <button key={p} type="button"
                    onClick={() => setPositions((prev) => (on ? prev.filter((x) => x !== p) : [...prev, p]))}
                    className="text-xs rounded-full px-3 py-1"
                    style={{ background: on ? "var(--accent-glow)" : "var(--background)", color: on ? "var(--accent)" : "var(--muted)", border: `1px solid ${on ? "var(--accent)" : "var(--border)"}` }}>
                    {p}
                  </button>
                );
              })}
            </div>
          </L>

          <L label="Giữ tệp (ngày)">
            <input type="number" min={1} max={365} value={retention} onChange={(e) => setRetention(Number(e.target.value) || 30)}
              className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={fieldStyle} />
          </L>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-xs font-medium"
            style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>Huỷ</button>
          <button onClick={save} disabled={saving || !workflowId || !!error}
            className="rounded-lg px-4 py-2 text-xs font-medium" style={{ background: "var(--accent)", color: "#fff" }}
            data-testid="save-schedule">{saving ? "..." : "Lưu"}</button>
        </div>
      </div>
    </div>
  );
}

function L({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>{label}</label>
      {children}
    </div>
  );
}
