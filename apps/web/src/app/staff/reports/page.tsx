"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  StaffReport, listStaffReports, downloadStaffReport, restoreStaffToken, staffMe, staffRefresh, EmployeeInfo,
} from "@/lib/api/staff";
import { useStaffSettings, getThemeVars } from "@/components/providers/StaffSettingsProvider";
import { BRAND_NAME } from "@/lib/brand";
import Markdown from "@/components/ui/Markdown";

const fmtTime = (iso: string) =>
  new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

const fmtSize = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

/** Reports the unit's schedules produced for this employee. */
export default function StaffReportsPage() {
  const router = useRouter();
  const { theme } = useStaffSettings();
  const vars = getThemeVars(theme);

  const [employee, setEmployee] = useState<EmployeeInfo | null>(null);
  const [reports, setReports] = useState<StaffReport[]>([]);
  const [open, setOpen] = useState<StaffReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setReports(await listStaffReports()); }
    catch (e: any) { setError(e.message || "Không tải được danh sách báo cáo"); }
    finally { setLoading(false); }
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

  return (
    <div style={{ minHeight: "100vh", background: vars["--s-bg"], color: vars["--s-text"] }}>
      <div className="mx-auto px-4 py-6" style={{ maxWidth: 900 }}>
        <div className="flex items-center justify-between mb-5">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: vars["--s-accent-text"] }}>{BRAND_NAME}</p>
            <h1 className="text-xl font-semibold">Báo cáo của tôi</h1>
            <p className="text-sm mt-0.5" style={{ color: vars["--s-text-muted"] }}>
              Báo cáo anh/chị đã tạo và báo cáo theo lịch gửi cho anh/chị — tải về để dùng trong công việc.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} className="text-xs rounded-lg px-3 py-2"
              style={{ background: vars["--s-bg-secondary"], color: vars["--s-text"], border: `1px solid ${vars["--s-border"]}` }}>↻</button>
            <button onClick={() => router.push("/staff/chat")} className="text-xs rounded-lg px-3 py-2"
              style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }} data-testid="back-to-chat">
              ← Hỏi đáp
            </button>
          </div>
        </div>

        {error && <div className="rounded-lg px-3 py-2 mb-3 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444" }}>{error}</div>}

        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: vars["--s-accent-text"] }} />
          </div>
        ) : reports.length === 0 ? (
          <div className="text-center py-16 rounded-xl" style={{ border: `1px dashed ${vars["--s-border"]}` }}>
            <p className="text-sm" style={{ color: vars["--s-text-muted"] }}>Chưa có báo cáo nào được gửi cho bạn.</p>
          </div>
        ) : (
          <div className="space-y-2" data-testid="staff-reports">
            {reports.map((r) => (
              <div key={r.id} className="rounded-xl p-4" style={{ background: vars["--s-bg-secondary"], border: `1px solid ${vars["--s-border"]}` }}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate">📄 {r.title || r.filename}</p>
                    <p className="text-[11px]" style={{ color: vars["--s-text-muted"] }}>
                      {fmtTime(r.created_at)} · {fmtSize(r.size)}
                      {r.schedule_name ? ` · lịch “${r.schedule_name}”` : ""}
                      {r.content_type.includes("word") ? " · Word" : r.content_type.includes("markdown") ? " · Markdown" : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {r.preview && (
                      <button onClick={() => setOpen(open?.id === r.id ? null : r)} className="text-xs rounded-lg px-3 py-1.5"
                        style={{ background: vars["--s-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-border"]}` }}
                        data-testid="preview-report">
                        {open?.id === r.id ? "Ẩn" : "Xem nhanh"}
                      </button>
                    )}
                    <button onClick={() => downloadStaffReport(r)} className="text-xs rounded-lg px-3 py-1.5 font-medium"
                      style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}
                      data-testid="download-report">
                      Tải về
                    </button>
                  </div>
                </div>
                {open?.id === r.id && r.preview && (
                  <div className="mt-3 pt-3 text-sm" style={{ borderTop: `1px solid ${vars["--s-border"]}` }} data-testid="report-preview">
                    <Markdown accent={vars["--s-accent-text"]}>{r.preview}</Markdown>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
