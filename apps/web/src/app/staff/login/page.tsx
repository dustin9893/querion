"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { staffLogin } from "@/lib/api/staff";
import { useStaffSettings, getThemeVars } from "@/components/providers/StaffSettingsProvider";
import { BRAND_NAME } from "@/lib/brand";

export default function StaffLoginPage() {
  const router = useRouter();
  const { theme, toggleTheme, locale, setLocale, t } = useStaffSettings();
  const vars = getThemeVars(theme);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await staffLogin(email, password);
      if (data.employee.must_change_password) {
        router.replace("/staff/change-password");
      } else {
        router.replace("/staff/chat");
      }
    } catch (err: any) {
      setError(err.message || t("loginError"));
    } finally {
      setLoading(false);
    }
  };

  const bgGradient = theme === "dark"
    ? "linear-gradient(135deg, #0b1220 0%, #1f2a44 50%, #0b1220 100%)"
    : "linear-gradient(135deg, #f7f7f9 0%, #ffe8d6 50%, #f7f7f9 100%)";

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: bgGradient, transition: "background 0.3s" }}>
      <div className="rounded-2xl p-8 relative" style={{
        background: theme === "dark" ? "rgba(17,26,46,0.9)" : "rgba(255,255,255,0.92)",
        border: `1px solid ${vars["--s-border"]}`,
        width: 400, backdropFilter: "blur(20px)", transition: "background 0.3s"
      }}>
        {/* Theme + Language toggle */}
        <div className="absolute top-4 right-4 flex items-center gap-2">
          <button onClick={() => setLocale(locale === "vi" ? "en" : "vi")}
            className="text-[10px] font-bold uppercase rounded px-1.5 py-0.5"
            style={{ background: vars["--s-accent-light"], color: vars["--s-accent-text"] }}>
            {locale === "vi" ? "VI" : "EN"}
          </button>
          <button onClick={toggleTheme} className="rounded p-1" style={{ color: vars["--s-text-secondary"] }}>
            {theme === "dark" ? (
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 2V3M8 13V14M2 8H3M13 8H14M3.75 3.75L4.5 4.5M11.5 11.5L12.25 12.25M12.25 3.75L11.5 4.5M4.5 11.5L3.75 12.25" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M14 9.32A6 6 0 016.68 2a6 6 0 107.32 7.32z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
            )}
          </button>
        </div>

        <div className="text-center mb-6">
          <div className="rounded-full p-3 mx-auto w-fit mb-3" style={{ background: vars["--s-accent-light"] }}>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" style={{ color: vars["--s-accent"] }}>
              <path d="M4 11L14 5L24 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M6 11V21M11 11V21M17 11V21M22 11V21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              <path d="M4 23H24" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </div>
          <p className="text-[11px] font-semibold uppercase tracking-wider mb-1" style={{ color: vars["--s-accent-text"] }}>{BRAND_NAME}</p>
          <h1 className="text-xl font-bold" style={{ color: vars["--s-text"] }}>{t("loginTitle")}</h1>
          <p className="text-sm mt-1" style={{ color: vars["--s-text-secondary"] }}>{t("loginSubtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg px-3 py-2 text-xs" style={{ background: "rgba(239,68,68,0.1)", color: "#f87171", border: "1px solid rgba(239,68,68,0.2)" }}>
              {error}
            </div>
          )}

          <div>
            <label className="text-[11px] font-semibold block mb-1.5" style={{ color: vars["--s-text-secondary"] }}>{t("email")}</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus
              className="w-full text-sm rounded-lg px-3 py-2.5 outline-none transition-all"
              placeholder="canbo@msb-demo.vn"
              style={{ background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}` }}
              onFocus={(e) => { e.target.style.borderColor = vars["--s-accent"]; }}
              onBlur={(e) => { e.target.style.borderColor = vars["--s-input-border"]; }} />
          </div>

          <div>
            <label className="text-[11px] font-semibold block mb-1.5" style={{ color: vars["--s-text-secondary"] }}>{t("password")}</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="w-full text-sm rounded-lg px-3 py-2.5 outline-none transition-all"
              placeholder="••••••••"
              style={{ background: vars["--s-input-bg"], color: vars["--s-text"], border: `1px solid ${vars["--s-input-border"]}` }}
              onFocus={(e) => { e.target.style.borderColor = vars["--s-accent"]; }}
              onBlur={(e) => { e.target.style.borderColor = vars["--s-input-border"]; }} />
          </div>

          <button type="submit" disabled={loading}
            className="w-full rounded-lg py-2.5 text-sm font-semibold transition-all"
            style={{ background: loading ? "#c9560f" : "linear-gradient(135deg, #ee6d1f, #f59e0b)", color: "#fff" }}>
            {loading ? "..." : t("loginButton")}
          </button>
        </form>

        <div className="text-center mt-5">
          <a href="/login" className="text-xs" style={{ color: vars["--s-text-muted"] }}>Quản trị hệ thống →</a>
        </div>
      </div>
    </div>
  );
}
