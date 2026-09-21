"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/components/providers/I18nProvider";
import { getDocumentChunks, updateChunk, ChunkResponse, ChunksPageResponse } from "@/lib/api/datasets";

interface Props {
  open: boolean;
  documentId: string;
  documentName: string;
  onClose: () => void;
}

export default function ChunksPreviewModal({ open, documentId, documentName, onClose }: Props) {
  const { t } = useI18n();
  const [data, setData] = useState<ChunksPageResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [expandedChunk, setExpandedChunk] = useState<string | null>(null);

  // Editing state
  const [editingChunkId, setEditingChunkId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<{ id: string; ok: boolean; msg: string } | null>(null);

  const fetchChunks = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    try {
      const result = await getDocumentChunks(documentId, page);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [documentId, page]);

  useEffect(() => {
    if (open) {
      setPage(1);
      setExpandedChunk(null);
      setEditingChunkId(null);
      setSaveStatus(null);
      fetchChunks();
    }
  }, [open, documentId]);

  useEffect(() => {
    if (open) fetchChunks();
  }, [page]);

  const startEditing = (chunk: ChunkResponse) => {
    setEditingChunkId(chunk.id);
    setEditContent(chunk.content);
    setExpandedChunk(chunk.id);
    setSaveStatus(null);
  };

  const cancelEditing = () => {
    setEditingChunkId(null);
    setEditContent("");
    setSaveStatus(null);
  };

  const saveChunk = async () => {
    if (!editingChunkId || !editContent.trim()) return;
    setSaving(true);
    setSaveStatus(null);
    try {
      const result = await updateChunk(editingChunkId, editContent);
      // Update local data
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          chunks: prev.chunks.map((c) =>
            c.id === editingChunkId ? { ...c, content: result.content } : c
          ),
        };
      });
      setSaveStatus({
        id: editingChunkId,
        ok: true,
        msg: result.re_embedded ? "Saved & re-embedded ✓" : "Saved (no embedding provider) ✓",
      });
      setEditingChunkId(null);
    } catch (err: any) {
      setSaveStatus({ id: editingChunkId, ok: false, msg: err.message || "Failed to save" });
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0" style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)" }} />

      {/* Modal */}
      <div
        className="relative w-full sm:w-[80%] lg:w-[60%] max-h-[90vh] flex flex-col rounded-t-2xl sm:rounded-2xl overflow-hidden"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
          <div className="min-w-0">
            <h3 className="text-lg font-semibold truncate" style={{ color: "var(--foreground)" }}>
              {t("chunks.title", "datasets")}
            </h3>
            <p className="text-sm truncate" style={{ color: "var(--muted)" }}>
              {documentName} — {data?.total ?? 0} chunks
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 rounded-lg p-2 transition-colors"
            style={{ color: "var(--muted)" }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "var(--foreground)"; e.currentTarget.style.background = "var(--card-hover)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.background = "transparent"; }}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M5 5L15 15M5 15L15 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5" style={{ maxHeight: "calc(90vh - 140px)" }}>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
            </div>
          ) : data?.chunks.length === 0 ? (
            <p className="text-center py-12 text-sm" style={{ color: "var(--muted)" }}>
              {t("chunks.empty", "datasets")}
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {data?.chunks.map((chunk) => {
                const isExpanded = expandedChunk === chunk.id;
                const isEditing = editingChunkId === chunk.id;
                const status = saveStatus?.id === chunk.id ? saveStatus : null;
                return (
                  <div
                    key={chunk.id}
                    className="rounded-xl p-4 transition-all duration-200"
                    style={{
                      background: "var(--background)",
                      border: isEditing
                        ? "1px solid var(--accent)"
                        : isExpanded
                        ? "1px solid var(--border)"
                        : "1px solid var(--border)",
                    }}
                  >
                    {/* Chunk header */}
                    <div className="flex items-center gap-2 mb-2">
                      <span
                        className="text-xs font-mono px-2 py-0.5 rounded"
                        style={{ background: "var(--accent-glow)", color: "var(--accent)" }}
                      >
                        #{chunk.chunk_index}
                      </span>
                      <span className="text-xs" style={{ color: "var(--muted)" }}>
                        {chunk.content.length} chars
                      </span>

                      {/* Status badge */}
                      {status && (
                        <span
                          className="text-xs px-2 py-0.5 rounded-full font-medium"
                          style={{
                            background: status.ok ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                            color: status.ok ? "#22c55e" : "#ef4444",
                          }}
                        >
                          {status.msg}
                        </span>
                      )}

                      <div className="ml-auto flex items-center gap-1">
                        {/* Edit button */}
                        {!isEditing && (
                          <button
                            onClick={(e) => { e.stopPropagation(); startEditing(chunk); }}
                            className="rounded-lg p-1.5 transition-colors"
                            style={{ color: "var(--muted)" }}
                            onMouseEnter={(e) => { e.currentTarget.style.color = "var(--accent)"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                            title="Edit chunk"
                          >
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                              <path d="M8.5 2.5L11.5 5.5M1 13H4L12 5C12.5523 4.44772 12.5523 3.55228 12 3L11 2C10.4477 1.44772 9.55228 1.44772 9 2L1 10V13Z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </button>
                        )}
                        {/* Expand/collapse */}
                        <button
                          onClick={(e) => { e.stopPropagation(); setExpandedChunk(isExpanded ? null : chunk.id); }}
                          className="rounded-lg p-1.5 transition-colors"
                          style={{ color: "var(--muted)" }}
                        >
                          <svg
                            width="14" height="14" viewBox="0 0 14 14" fill="none"
                            className="transition-transform duration-200"
                            style={{ transform: isExpanded ? "rotate(180deg)" : "none" }}
                          >
                            <path d="M3 5L7 9L11 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                          </svg>
                        </button>
                      </div>
                    </div>

                    {/* Content: edit mode or view mode */}
                    {isEditing ? (
                      <div>
                        <textarea
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          className="w-full rounded-lg p-3 text-sm outline-none resize-y font-mono"
                          style={{
                            background: "var(--card)",
                            border: "1px solid var(--border)",
                            color: "var(--foreground)",
                            minHeight: 160,
                            maxHeight: 400,
                          }}
                          autoFocus
                        />
                        <div className="flex items-center gap-2 mt-2">
                          <button
                            onClick={saveChunk}
                            disabled={saving || !editContent.trim()}
                            className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
                            style={{ background: "var(--accent)" }}
                          >
                            {saving ? "Saving..." : "Save & Re-embed"}
                          </button>
                          <button
                            onClick={cancelEditing}
                            className="rounded-lg px-3 py-1.5 text-xs"
                            style={{ color: "var(--muted)" }}
                          >
                            Cancel
                          </button>
                          <span className="text-xs ml-auto" style={{ color: "var(--muted)" }}>
                            {editContent.length} chars
                          </span>
                        </div>
                      </div>
                    ) : (
                      <p
                        className="text-sm leading-relaxed cursor-pointer"
                        style={{
                          color: "var(--foreground)",
                          display: "-webkit-box",
                          WebkitLineClamp: isExpanded ? 999 : 3,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                          whiteSpace: "pre-wrap",
                        }}
                        onClick={() => setExpandedChunk(isExpanded ? null : chunk.id)}
                      >
                        {chunk.content}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer — Pagination */}
        {totalPages > 1 && (
          <div
            className="flex items-center justify-between px-5 py-3"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40"
              style={{ color: "var(--accent)" }}
            >
              ← {t("chunks.prev", "datasets")}
            </button>
            <span className="text-sm" style={{ color: "var(--muted)" }}>
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40"
              style={{ color: "var(--accent)" }}
            >
              {t("chunks.next", "datasets")} →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
