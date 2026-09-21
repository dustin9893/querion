"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useI18n } from "@/components/providers/I18nProvider";
import { getDataset, deleteDocument, indexDocument, getDocument, updateDataset, setDocumentEnabled, DatasetDetailResponse, DocumentResponse } from "@/lib/api/datasets";
import VisibilityBadge from "@/components/datasets/VisibilityBadge";
import UploadDropzone from "@/components/datasets/UploadDropzone";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import Toggle from "@/components/ui/Toggle";
import ChunksPreviewModal from "@/components/datasets/ChunksPreviewModal";

const STATUS_STYLES: Record<string, { bg: string; color: string }> = {
  uploaded: { bg: "rgba(156,163,175,0.15)", color: "#9ca3af" },
  indexing: { bg: "rgba(234,179,8,0.15)", color: "#eab308" },
  ready: { bg: "rgba(34,197,94,0.15)", color: "#22c55e" },
  failed: { bg: "rgba(239,68,68,0.15)", color: "#ef4444" },
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DatasetDetailPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useParams();
  const datasetId = params.datasetId as string;
  const [dataset, setDataset] = useState<DatasetDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteDocTarget, setDeleteDocTarget] = useState<DocumentResponse | null>(null);
  const [chunksDoc, setChunksDoc] = useState<DocumentResponse | null>(null);
  const pollingRef = useRef<Record<string, NodeJS.Timeout>>({});

  const fetchDataset = useCallback(async () => {
    try {
      const data = await getDataset(datasetId);
      setDataset(data);
      // Auto-start polling for any documents currently indexing
      data.documents.forEach((doc) => {
        if (doc.status === "indexing") {
          startPolling(doc.id);
        }
      });
    } catch {
      router.push("/datasets");
    } finally {
      setLoading(false);
    }
  }, [datasetId, router]);

  useEffect(() => { fetchDataset(); }, [fetchDataset]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      Object.values(pollingRef.current).forEach(clearInterval);
    };
  }, []);

  const startPolling = (docId: string) => {
    if (pollingRef.current[docId]) return;
    pollingRef.current[docId] = setInterval(async () => {
      try {
        const doc = await getDocument(docId);
        if (doc.status !== "indexing") {
          clearInterval(pollingRef.current[docId]);
          delete pollingRef.current[docId];
          fetchDataset();
        }
      } catch {
        clearInterval(pollingRef.current[docId]);
        delete pollingRef.current[docId];
      }
    }, 3000);
  };

  const handleIndex = async (doc: DocumentResponse) => {
    try {
      await indexDocument(doc.id);
      // Optimistically update status
      setDataset((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          documents: prev.documents.map((d) =>
            d.id === doc.id ? { ...d, status: "indexing" as const } : d
          ),
        };
      });
      startPolling(doc.id);
    } catch (err: any) {
      alert(err.message || "Failed to start indexing");
    }
  };

  const handleToggleEnabled = async (doc: DocumentResponse, enabled: boolean) => {
    const patchDoc = (fields: Partial<DocumentResponse>) =>
      setDataset((prev) => prev && { ...prev, documents: prev.documents.map((d) => (d.id === doc.id ? { ...d, ...fields } : d)) });
    patchDoc({ enabled });  // optimistic
    try {
      const updated = await setDocumentEnabled(doc.id, enabled);
      patchDoc({ enabled: updated.enabled, disabled_at: updated.disabled_at });
    } catch (err: any) {
      patchDoc({ enabled: doc.enabled, disabled_at: doc.disabled_at });
      alert(err.message || t("detail.enableFailed", "datasets"));
    }
  };

  const toggleVisibility = async () => {
    if (!dataset) return;
    const next = dataset.visibility === "public" ? "internal" : "public";
    try {
      const updated = await updateDataset(dataset.id, { visibility: next });
      setDataset((prev) => (prev ? { ...prev, visibility: updated.visibility } : prev));
    } catch (err: any) {
      alert(err.message || "Failed to update visibility");
    }
  };

  const handleDeleteDocConfirmed = async () => {
    if (!deleteDocTarget) return;
    await deleteDocument(deleteDocTarget.id);
    setDeleteDocTarget(null);
    await fetchDataset();
  };

  if (loading || !dataset) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="dataset-detail-header flex items-center gap-3 mb-6">
        <button
          onClick={() => router.push("/datasets")}
          className="rounded-lg p-2 transition-all duration-200"
          style={{ color: "var(--muted)" }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--foreground)"; e.currentTarget.style.background = "var(--card-hover)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.background = "transparent"; }}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M13 4L7 10L13 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>{dataset.name}</h2>
            <button onClick={toggleVisibility} title={t("detail.toggleVisibility", "datasets")} className="rounded-full">
              <VisibilityBadge visibility={dataset.visibility} label={t(`visibility.${dataset.visibility}`, "datasets")} />
            </button>
          </div>
          {dataset.description && <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>{dataset.description}</p>}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {dataset.documents.some((d) => d.status === "ready" && d.enabled) && (
            <button
              onClick={() => router.push(`/datasets/${datasetId}/chat`)}
              className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all"
              style={{ background: "var(--accent)", color: "#fff" }}
              onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.9"; }}
              onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 2C4.24 2 2 3.97 2 6.5C2 7.87 2.73 9.1 3.88 9.93L3 12L5.7 10.75C6.12 10.86 6.55 10.92 7 10.92C9.76 10.92 12 8.97 12 6.5C12 3.97 9.76 2 7 2Z" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
              </svg>
              {t("detail.chat", "datasets")}
            </button>
          )}
          <span
            className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium"
            style={{ background: "var(--accent-glow)", color: "var(--accent)" }}
          >
            {dataset.document_count} {t("detail.documents", "datasets")}
            {dataset.documents.some((d) => !d.enabled) && (
              <> · {dataset.documents.filter((d) => !d.enabled).length} {t("detail.disabledCount", "datasets")}</>
            )}
          </span>
        </div>
      </div>

      {/* Upload */}
      <div className="mb-6">
        <UploadDropzone datasetId={datasetId} onUploadComplete={fetchDataset} />
      </div>

      {/* Documents Table */}
      {dataset.documents.length === 0 ? (
        <div
          className="flex items-center justify-center rounded-xl py-12"
          style={{ border: "1px dashed var(--border)", background: "var(--card)" }}
        >
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            {t("detail.noDocuments", "datasets")}
          </p>
        </div>
      ) : (
        <div className="responsive-table-wrap rounded-xl overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>{t("detail.filename", "datasets")}</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>{t("detail.meta", "datasets")}</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>{t("detail.size", "datasets")}</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>{t("detail.status", "datasets")}</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>Chunks</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }} title={t("detail.enabledHint", "datasets")}>{t("detail.enabled", "datasets")}</th>
                <th className="text-right px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>{t("detail.actions", "datasets")}</th>
              </tr>
            </thead>
            <tbody>
              {dataset.documents.map((doc) => {
                const style = STATUS_STYLES[doc.status] || STATUS_STYLES.uploaded;
                const isIndexing = doc.status === "indexing";
                return (
                  <tr key={doc.id} data-testid={`doc-row-${doc.filename}`} style={{ borderBottom: "1px solid var(--border)", background: doc.enabled ? undefined : "var(--card-hover)" }}>
                    <td className="px-4 py-3" style={{ opacity: doc.enabled ? 1 : 0.55 }}>
                      <button
                        className="flex items-center gap-2 text-left"
                        onClick={() => doc.status === "ready" ? setChunksDoc(doc) : undefined}
                        style={{ cursor: doc.status === "ready" ? "pointer" : "default" }}
                      >
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" style={{ color: "var(--muted)", flexShrink: 0 }}>
                          <path d="M4 2H10.5L14 5.5V16H4V2Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                          <path d="M10 2V6H14" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                        </svg>
                        <span
                          className="font-medium truncate"
                          style={{
                            color: doc.status === "ready" ? "var(--accent)" : "var(--foreground)",
                            maxWidth: 240,
                            textDecoration: doc.status === "ready" ? "underline" : "none",
                            textDecorationColor: "var(--accent-glow)",
                          }}
                        >
                          {doc.filename}
                        </span>
                      </button>
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--muted)", opacity: doc.enabled ? 1 : 0.55 }}>
                      {[
                        doc.doc_type ? t(`docType.${doc.doc_type}`, "datasets") : null,
                        doc.version,
                        doc.effective_from ? `HL ${doc.effective_from}` : null,
                      ].filter(Boolean).join(" · ") || "—"}
                    </td>
                    <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{formatBytes(doc.size)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${isIndexing ? "animate-pulse" : ""}`}
                        style={{ background: style.bg, color: style.color }}
                      >
                        {isIndexing && (
                          <svg className="animate-spin mr-1" width="12" height="12" viewBox="0 0 12 12" fill="none">
                            <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="20" strokeDashoffset="10" />
                          </svg>
                        )}
                        {t(`status.${doc.status}`, "datasets")}
                      </span>
                      {doc.status === "failed" && doc.error_message && (
                        <div
                          className="mt-1 text-[11px] leading-snug max-w-[240px] line-clamp-2"
                          style={{ color: "#ef4444" }}
                          title={doc.error_message}
                          data-testid={`doc-error-${doc.filename}`}
                        >
                          {doc.error_message}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {doc.status === "ready" ? (
                        <button
                          onClick={() => setChunksDoc(doc)}
                          className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium"
                          style={{ background: "var(--accent-glow)", color: "var(--accent)" }}
                        >
                          {doc.chunk_count} chunks
                        </button>
                      ) : (
                        <span className="text-xs" style={{ color: "var(--muted)" }}>—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Toggle
                          on={doc.enabled}
                          onChange={(v) => handleToggleEnabled(doc, v)}
                          label={t(doc.enabled ? "detail.disable" : "detail.enable", "datasets")}
                          testId={`doc-enabled-${doc.filename}`}
                        />
                        {!doc.enabled && (
                          <span
                            className="text-xs whitespace-nowrap"
                            style={{ color: "var(--muted)" }}
                            title={doc.disabled_at ? `${t("detail.disabledAt", "datasets")} ${new Date(doc.disabled_at).toLocaleString("vi-VN")}` : undefined}
                          >
                            {t("detail.disabled", "datasets")}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {/* Index button */}
                        {(doc.status === "uploaded" || doc.status === "failed") && (
                          <button
                            onClick={() => handleIndex(doc)}
                            className="rounded-lg px-2.5 py-1 text-xs font-medium transition-all duration-200"
                            style={{
                              color: "var(--accent)",
                              border: "1px solid var(--accent)",
                              background: "transparent",
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = "var(--accent-glow)"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                          >
                            {t("detail.index", "datasets")}
                          </button>
                        )}
                        {/* Delete button */}
                        <button
                          onClick={() => setDeleteDocTarget(doc)}
                          className="rounded-lg p-1.5 transition-all duration-200"
                          style={{ color: "var(--muted)" }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; e.currentTarget.style.background = "rgba(239,68,68,0.1)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.background = "transparent"; }}
                        >
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <path d="M3 4H13M5.5 4V3C5.5 2.44772 5.94772 2 6.5 2H9.5C10.0523 2 10.5 2.44772 10.5 3V4M6.5 7V11M9.5 7V11M4 4L4.5 13C4.5 13.5523 4.94772 14 5.5 14H10.5C11.0523 14 11.5 13.5523 11.5 13L12 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteDocTarget}
        message={t("detail.deleteConfirm", "datasets")}
        variant="danger"
        onConfirm={handleDeleteDocConfirmed}
        onCancel={() => setDeleteDocTarget(null)}
      />

      <ChunksPreviewModal
        open={!!chunksDoc}
        documentId={chunksDoc?.id || ""}
        documentName={chunksDoc?.filename || ""}
        onClose={() => setChunksDoc(null)}
      />
    </div>
  );
}
