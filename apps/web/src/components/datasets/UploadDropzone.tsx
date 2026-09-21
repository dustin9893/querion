"use client";

import { useCallback, useRef, useState } from "react";
import { useI18n } from "@/components/providers/I18nProvider";
import { DOC_TYPES } from "@/lib/api/datasets";
import { KB_ACCEPT } from "@/lib/kbFormats";

interface Props {
  datasetId: string;
  onUploadComplete: () => void;
}

const fieldStyle = { background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" };

export default function UploadDropzone({ datasetId, onUploadComplete }: Props) {
  const { t } = useI18n();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  // Banking metadata applied to every file in this upload batch
  const [docType, setDocType] = useState<string>("");
  const [version, setVersion] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");

  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    const { api } = await import("@/lib/api");
    const fileArr = Array.from(files);
    if (fileArr.length === 0) return;

    setUploading(true);
    setProgress([]);

    for (const file of fileArr) {
      try {
        setProgress((prev) => [...prev, `${t("upload.uploading", "datasets")} ${file.name}`]);
        const formData = new FormData();
        formData.append("file", file);
        if (docType) formData.append("doc_type", docType);
        if (version.trim()) formData.append("version", version.trim());
        if (effectiveFrom.trim()) formData.append("effective_from", effectiveFrom.trim());
        await api.upload(`/v1/datasets/${datasetId}/documents/upload`, formData);
        setProgress((prev) => [...prev.slice(0, -1), `✓ ${file.name}`]);
      } catch (err: any) {
        setProgress((prev) => [...prev.slice(0, -1), `✗ ${file.name}: ${err.message}`]);
      }
    }

    setUploading(false);
    onUploadComplete();
    setTimeout(() => setProgress([]), 3000);
  }, [datasetId, onUploadComplete, docType, version, effectiveFrom, t]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  }, [uploadFiles]);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      // Capture files into array BEFORE resetting input
      // (FileList is a live reference that gets cleared when input value is reset)
      const fileArray = Array.from(files);
      e.target.value = "";
      uploadFiles(fileArray);
    }
  }, [uploadFiles]);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  return (
    <div className="rounded-xl" style={{ border: "1px solid var(--border)", background: "var(--card)" }}>
      {/* Metadata row */}
      <div className="grid gap-3 p-4 sm:grid-cols-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div>
          <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--muted)" }}>{t("upload.docTypeLabel", "datasets")}</label>
          <select value={docType} onChange={(e) => setDocType(e.target.value)}
            className="w-full rounded-lg px-3 py-2 text-sm outline-none" style={fieldStyle}>
            <option value="">—</option>
            {DOC_TYPES.map((k) => <option key={k} value={k}>{t(`docType.${k}`, "datasets")}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--muted)" }}>{t("upload.versionLabel", "datasets")}</label>
          <input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="v3.2"
            className="w-full rounded-lg px-3 py-2 text-sm outline-none" style={fieldStyle} />
        </div>
        <div>
          <label className="block text-[11px] font-semibold mb-1" style={{ color: "var(--muted)" }}>{t("upload.effectiveLabel", "datasets")}</label>
          <input value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} placeholder="01/03/2026"
            className="w-full rounded-lg px-3 py-2 text-sm outline-none" style={fieldStyle} />
        </div>
        <p className="sm:col-span-3 text-[11px]" style={{ color: "var(--muted)" }}>{t("upload.metaHint", "datasets")}</p>
      </div>

      {/* Dropzone */}
      <div
        className="p-6 text-center transition-all duration-200 cursor-pointer rounded-b-xl"
        style={{
          border: `2px dashed ${dragging ? "var(--accent)" : "transparent"}`,
          background: dragging ? "var(--accent-glow)" : "transparent",
        }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={openFilePicker}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={KB_ACCEPT}
          multiple
          style={{ display: "none" }}
          onChange={handleFileSelect}
          onClick={(e) => e.stopPropagation()}
        />

        <svg width="40" height="40" viewBox="0 0 40 40" fill="none" className="mx-auto mb-3">
          <path d="M20 8V24M14 14L20 8L26 14" stroke={dragging ? "var(--accent)" : "var(--muted)"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M8 28V30C8 31.1046 8.89543 32 10 32H30C31.1046 32 32 31.1046 32 30V28" stroke={dragging ? "var(--accent)" : "var(--muted)"} strokeWidth="2" strokeLinecap="round" />
        </svg>

        {uploading ? (
          <p className="text-sm font-medium" style={{ color: "var(--accent)" }}>
            {t("upload.uploading", "datasets")}
          </p>
        ) : (
          <>
            <p className="text-sm font-medium" style={{ color: "var(--foreground)" }}>
              {t("upload.title", "datasets")}
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
              {t("upload.subtitle", "datasets")}
            </p>
          </>
        )}

        {progress.length > 0 && (
          <div className="mt-3 text-left text-xs space-y-1">
            {progress.map((msg, i) => (
              <p key={i} style={{ color: msg.startsWith("✗") ? "#ef4444" : msg.startsWith("✓") ? "#22c55e" : "var(--muted)" }}>
                {msg}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
