"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/components/providers/I18nProvider";
import { WorkflowResponse, createWorkflow, updateWorkflow, listWorkflows, deleteWorkflow } from "@/lib/api/workflows";

export default function WorkflowsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [workflows, setWorkflows] = useState<WorkflowResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null); // workflow id to delete

  const fetchWorkflows = useCallback(async () => {
    try {
      const data = await listWorkflows();
      setWorkflows(data);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchWorkflows(); }, [fetchWorkflows]);

  /** A report starts from a working skeleton: parameters → file → end. */
  const handleCreateReport = async () => {
    setCreating(true);
    try {
      const wf = await createWorkflow("Báo cáo mới", "report", "Báo cáo chạy nền, xuất tệp tải về được");
      await updateWorkflow(wf.id, { graph_json: {
        nodes: [
          { id: "input", type: "input", position: { x: 0, y: 140 }, data: { label: "Tham số báo cáo", fields: [] } },
          { id: "xuat", type: "render_document", position: { x: 320, y: 140 }, data: {
            label: "Xuất tài liệu", format: "markdown", audience: "admin",
            title: "Báo cáo {{ today }}", filename: "bao-cao-{{ today }}",
            template: "# Báo cáo {{ today }}\n\nThêm node Gọi công cụ / Tra kho tri thức / LLM trước node này,\nrồi dùng {{ '{{ tool_results }}' }} và {{ '{{ answer }}' }} trong mẫu.\n", vars: {},
          } },
          { id: "output", type: "output", position: { x: 640, y: 140 }, data: { label: "Kết thúc" } },
        ],
        edges: [
          { id: "e1", source: "input", target: "xuat" },
          { id: "e2", source: "xuat", target: "output" },
        ],
      } });
      router.push(`/workflows/${wf.id}`);
    } catch { /* silent */ }
    finally { setCreating(false); }
  };

  const handleCreate = async () => {
    setCreating(true);
    try {
      const wf = await createWorkflow("Untitled Workflow");
      router.push(`/workflows/${wf.id}`);
    } catch { /* silent */ }
    finally { setCreating(false); }
  };

  const confirmDelete = async () => {
    if (!deleting) return;
    try {
      await deleteWorkflow(deleting);
      setWorkflows((prev) => prev.filter((w) => w.id !== deleting));
    } catch { /* silent */ }
    finally { setDeleting(null); }
  };

  const deletingWorkflow = workflows.find((w) => w.id === deleting);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
            {t("nav.workflows")}
          </h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
            Build RAG pipelines with a visual editor
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCreateReport}
            disabled={creating}
            className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all"
            style={{ background: "var(--card)", color: "var(--foreground)", border: "1px solid var(--border)" }}
            data-testid="new-report"
          >
            📄 Luồng báo cáo
          </button>
          <button
            onClick={handleCreate}
            disabled={creating}
            className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-all"
            style={{ background: "var(--accent)", color: "#fff" }}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            New Workflow
          </button>
        </div>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : workflows.length === 0 ? (
        <div className="text-center py-20">
          <div className="rounded-full p-4 mb-4 mx-auto w-fit" style={{ background: "var(--accent-glow)" }}>
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" style={{ color: "var(--accent)" }}>
              <path d="M6 6H12V12H6V6Z" stroke="currentColor" strokeWidth="1.5" />
              <path d="M20 20H26V26H20V20Z" stroke="currentColor" strokeWidth="1.5" />
              <path d="M12 9H20V9C20 13 17 16 13 16V16" stroke="currentColor" strokeWidth="1.5" />
              <path d="M13 16V23H20" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--foreground)" }}>No workflows yet</h3>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Create your first visual RAG pipeline</p>
        </div>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {workflows.map((wf) => (
            <div
              key={wf.id}
              onClick={() => router.push(`/workflows/${wf.id}`)}
              className="rounded-xl p-4 cursor-pointer transition-all group"
              style={{ background: "var(--card)", border: "1px solid var(--border)" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; e.currentTarget.style.boxShadow = "0 0 0 1px var(--accent)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.boxShadow = "none"; }}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <div className="rounded-lg p-1.5" style={{ background: "var(--accent-glow)" }}>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ color: "var(--accent)" }}>
                      <path d="M3 3H7V7H3V3Z" stroke="currentColor" strokeWidth="1" />
                      <path d="M9 9H13V13H9V9Z" stroke="currentColor" strokeWidth="1" />
                      <path d="M7 5H9V5C9 7 8 8 6 8" stroke="currentColor" strokeWidth="1" />
                      <path d="M6 8V11H9" stroke="currentColor" strokeWidth="1" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>{wf.name}</h3>
                    <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded-full"
                      style={{
                        background: wf.type === "chatflow" ? "rgba(236,72,153,0.12)" : wf.type === "report" ? "rgba(132,204,22,0.12)" : "rgba(168,85,247,0.12)",
                        color: wf.type === "chatflow" ? "#ec4899" : wf.type === "report" ? "#84cc16" : "#a855f7",
                      }}>
                      {wf.type || "chatflow"}
                    </span>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleting(wf.id); }}
                  className="opacity-0 group-hover:opacity-100 rounded-lg p-1 transition-all"
                  style={{ color: "var(--muted)" }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M4 4L10 10M4 10L10 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
              {wf.description && <p className="text-xs mb-2 line-clamp-2" style={{ color: "var(--muted)" }}>{wf.description}</p>}
              <div className="flex items-center gap-3 text-xs" style={{ color: "var(--muted)" }}>
                <span>{wf.node_count} nodes</span>
                <span>·</span>
                <span>{new Date(wf.updated_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleting && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
          onClick={() => setDeleting(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="rounded-2xl p-6"
            style={{ background: "var(--card)", border: "1px solid var(--border)", width: 400 }}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="rounded-full p-2" style={{ background: "rgba(239,68,68,0.1)" }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style={{ color: "#ef4444" }}>
                  <path d="M10 6V10M10 14H10.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>Delete Workflow</h3>
                <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                  Are you sure you want to delete <strong>{deletingWorkflow?.name || "this workflow"}</strong>? This action cannot be undone.
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleting(null)}
                className="rounded-lg px-4 py-2 text-xs font-medium transition-all"
                style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                className="rounded-lg px-4 py-2 text-xs font-medium transition-all"
                style={{ background: "#ef4444", color: "#fff" }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
