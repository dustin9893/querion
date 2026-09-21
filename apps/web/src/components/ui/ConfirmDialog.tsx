"use client";

import { useI18n } from "@/components/providers/I18nProvider";

interface Props {
  open: boolean;
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  variant = "danger",
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useI18n();

  if (!open) return null;

  const confirmText = confirmLabel || t("buttons.delete", "common");
  const cancelText = cancelLabel || t("buttons.cancel", "common");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)" }}
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-2xl p-6 animate-in fade-in zoom-in-95"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          boxShadow: "0 25px 50px rgba(0,0,0,0.3)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Icon */}
        <div
          className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full"
          style={{
            background: variant === "danger" ? "rgba(239,68,68,0.12)" : "rgba(59,130,246,0.12)",
          }}
        >
          {variant === "danger" ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 9V13M12 17H12.01M10.29 3.86L1.82 18C1.64 18.3 1.55 18.65 1.55 19C1.55 19.35 1.64 19.7 1.82 20C2 20.3 2.26 20.56 2.56 20.74C2.86 20.92 3.21 21.01 3.56 21H20.49C20.84 21.01 21.19 20.92 21.49 20.74C21.79 20.56 22.05 20.3 22.23 20C22.41 19.7 22.5 19.35 22.5 19C22.5 18.65 22.41 18.3 22.23 18L13.76 3.86C13.58 3.56 13.32 3.32 13.02 3.14C12.72 2.97 12.38 2.88 12.03 2.88C11.68 2.88 11.34 2.97 11.04 3.14C10.74 3.32 10.48 3.56 10.29 3.86Z"
                stroke="#ef4444"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="#3b82f6" strokeWidth="1.5" />
              <path d="M12 8V12M12 16H12.01" stroke="#3b82f6" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          )}
        </div>

        {/* Title */}
        {title && (
          <h3 className="text-center text-base font-semibold mb-2" style={{ color: "var(--foreground)" }}>
            {title}
          </h3>
        )}

        {/* Message */}
        <p className="text-center text-sm mb-6" style={{ color: "var(--muted)" }}>
          {message}
        </p>

        {/* Buttons */}
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg px-4 py-2.5 text-sm font-medium transition-all duration-200"
            style={{ color: "var(--foreground)", border: "1px solid var(--border)" }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "var(--card-hover)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-all duration-200"
            style={{
              background: variant === "danger" ? "#ef4444" : "var(--accent)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = variant === "danger" ? "#dc2626" : "var(--accent-hover)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = variant === "danger" ? "#ef4444" : "var(--accent)";
            }}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
