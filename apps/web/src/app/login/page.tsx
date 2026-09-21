"use client";

import Image from "next/image";
import { useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { useI18n } from "@/components/providers/I18nProvider";

export default function LoginPage() {
  const { login } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4"
      style={{ background: "var(--background)" }}
    >
      <div
        className="w-full max-w-md rounded-2xl p-8"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
        }}
      >
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <Image src="/icon.png" alt="Brand" width={56} height={56} className="rounded-2xl mb-4" />
          <h1 className="text-2xl font-bold" style={{ color: "var(--foreground)" }}>
            {t("appName")}
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
            Đăng nhập tài khoản quản trị
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && (
            <div
              className="rounded-lg px-4 py-3 text-sm"
              style={{ background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}
            >
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--foreground)" }}>
              Email
            </label>
            <input
              id="login-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@querion.io"
              required
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all duration-200"
              style={{
                background: "var(--background)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--foreground)" }}>
              Password
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full rounded-lg px-4 py-2.5 text-sm outline-none transition-all duration-200"
              style={{
                background: "var(--background)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
              }}
              onFocus={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}
            />
          </div>

          <button
            id="login-submit"
            type="submit"
            disabled={loading}
            className="w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white transition-all duration-200 mt-2"
            style={{
              background: loading ? "var(--muted)" : "var(--accent)",
              cursor: loading ? "not-allowed" : "pointer",
            }}
            onMouseOver={(e) => { if (!loading) e.currentTarget.style.background = "var(--accent-hover)"; }}
            onMouseOut={(e) => { if (!loading) e.currentTarget.style.background = "var(--accent)"; }}
          >
            {loading ? "Đang đăng nhập..." : "Đăng nhập"}
          </button>
        </form>

        <p className="text-xs text-center mt-6" style={{ color: "var(--muted)" }}>
          {t("appName")} {t("version")}
        </p>
      </div>
    </div>
  );
}
