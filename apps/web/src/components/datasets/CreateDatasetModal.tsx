"use client";

import { useState } from "react";
import { useI18n } from "@/components/providers/I18nProvider";
import type { DatasetVisibility } from "@/lib/api/datasets";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, description?: string, visibility?: DatasetVisibility) => Promise<void>;
}

const fieldStyle = { background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" };

export default function CreateDatasetModal({ open, onClose, onCreate }: Props) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<DatasetVisibility>("internal");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      await onCreate(name.trim(), description.trim() || undefined, visibility);
      setName("");
      setDescription("");
      setVisibility("internal");
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.5)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl p-6"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold mb-4" style={{ color: "var(--foreground)" }}>
          {t("modal.title", "datasets")}
        </h3>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--foreground)" }}>
              {t("modal.nameLabel", "datasets")}
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("modal.namePlaceholder", "datasets")}
              required
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all duration-200"
              style={fieldStyle}
              onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--foreground)" }}>
              {t("modal.descLabel", "datasets")}
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("modal.descPlaceholder", "datasets")}
              rows={3}
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all duration-200 resize-none"
              style={fieldStyle}
              onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--foreground)" }}>
              {t("modal.visibilityLabel", "datasets")}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {(["internal", "public"] as DatasetVisibility[]).map((v) => {
                const active = visibility === v;
                return (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setVisibility(v)}
                    className="rounded-lg px-3 py-2.5 text-left text-xs transition-all"
                    style={{
                      background: active ? "var(--accent-glow)" : "var(--background)",
                      border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                      color: active ? "var(--accent-hover)" : "var(--foreground)",
                    }}
                  >
                    <span className="block font-semibold">{t(`visibility.${v}`, "datasets")}</span>
                    <span className="block mt-0.5" style={{ color: "var(--muted)" }}>{t(`visibility.${v}Hint`, "datasets")}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200"
              style={{ color: "var(--muted)", border: "1px solid var(--border)" }}
            >
              {t("modal.cancel", "datasets")}
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="rounded-lg px-4 py-2 text-sm font-semibold text-white transition-all duration-200"
              style={{ background: loading ? "var(--muted)" : "var(--accent)", cursor: loading ? "not-allowed" : "pointer" }}
            >
              {loading ? t("modal.creating", "datasets") : t("modal.create", "datasets")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
