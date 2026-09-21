"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { staffChangePassword, restoreStaffToken } from "@/lib/api/staff";
import { useStaffSettings, getThemeVars } from "@/components/providers/StaffSettingsProvider";

export default function ChangePasswordPage() {
  const router = useRouter();
  const { theme, t } = useStaffSettings();
  const vars = getThemeVars(theme);

  const [newPwd, setNewPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (newPwd.length < 6) { setError(t("passwordTooShort")); return; }
    if (newPwd !== confirm) { setError(t("passwordMismatch")); return; }

    setLoading(true);
    try {
      if (!restoreStaffToken()) { router.replace("/staff/login"); return; }
      await staffChangePassword(newPwd);
      router.replace("/staff/chat");
    } catch (err: any) {
      setError(err.message || "Failed to change password");
    } finally {
      setLoading(false);
    }
  };

  const bgGradient = theme === "dark"
    ? "linear-gradient(135deg, #0b1220 0%, #1f2a44 50%, #0b1220 100%)"
    : "linear-gradient(135deg, #f7f7f9 0%, #fef3c7 50%, #f7f7f9 100%)";

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: bgGradient, transition: "background 0.3s" }}>
      <div className="rounded-2xl p-8" style={{
        background: theme === "dark" ? "rgba(17,26,46,0.9)" : "rgba(255,255,255,0.92)",
        border: `1px solid ${vars["--s-border"]}`, width: 400, backdropFilter: "blur(20px)", transition: "background 0.3s"
      }}>
        <div className="text-center mb-6">
          <div className="rounded-full p-3 mx-auto w-fit mb-3" style={{ background: "rgba(245,158,11,0.15)" }}>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" style={{ color: "#f59e0b" }}>
              <path d="M14 6V14M14 18H14.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="14" cy="14" r="11" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </div>
          <h1 className="text-xl font-bold" style={{ color: vars["--s-text"] }}>{t("changePasswordTitle")}</h1>
          <p className="text-sm mt-1" style={{ color: vars["--s-text-secondary"] }}>{t("changePasswordSubtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#f87171", border: "1px solid rgba(239,68,68,0.2)" }}>
              {error}
            </div>
          )}
          <div>
            <label className="text-[11px] font-semibold block mb-1.5" style={{ color: vars["--s-text-secondary"] }}>{t("newPassword")}</label>
            <input type="password" value={newPwd} onChange={(e) => setNewPwd(e.target.value)} required autoFocus
              className="w-full text-sm rounded-lg px-3 py-2.5 outline-none transition-all"
              placeholder="••••••••"
              style={{ background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}` }} />
          </div>
          <div>
            <label className="text-[11px] font-semibold block mb-1.5" style={{ color: vars["--s-text-secondary"] }}>{t("confirmPassword")}</label>
            <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required
              className="w-full text-sm rounded-lg px-3 py-2.5 outline-none transition-all"
              placeholder="••••••••"
              style={{ background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}` }} />
          </div>
          <button type="submit" disabled={loading}
            className="w-full rounded-lg py-2.5 text-sm font-semibold transition-all"
            style={{ background: "linear-gradient(135deg, #f59e0b, #d97706)", color: "#fff" }}>
            {loading ? "..." : t("changePasswordButton")}
          </button>
        </form>
      </div>
    </div>
  );
}
