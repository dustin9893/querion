"use client";

import { useAuth } from "@/components/providers/AuthProvider";
import { useI18n } from "@/components/providers/I18nProvider";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

interface ProviderItem {
  id: string;
  provider_name: string;
  display_name: string;
  api_key_masked: string;
  model_name: string;
  purpose: string;
  base_url?: string | null;
  is_active: boolean;
  created_at: string;
}

interface ModelDef {
  provider: string;
  model: string;
  purpose: string;
  dimensions: number | null;
  label: string;
}

interface ProviderDef {
  value: string;
  label: string;
  base_url?: string | null;
}

const PURPOSE_OPTIONS = [
  { value: "embedding", label: "Embedding" },
  { value: "llm", label: "LLM" },
];

const PURPOSE_COLORS: Record<string, { bg: string; color: string }> = {
  embedding: { bg: "rgba(168,85,247,0.15)", color: "#a855f7" },
  llm: { bg: "rgba(59,130,246,0.15)", color: "#3b82f6" },
};

export default function AdminSettingsPage() {
  const { isSuper } = useAuth();
  const { t } = useI18n();
  const [providers, setProviders] = useState<ProviderItem[]>([]);
  const [allModels, setAllModels] = useState<ModelDef[]>([]);
  const [providerDefs, setProviderDefs] = useState<ProviderDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    provider_name: "openai",
    purpose: "embedding",
    model_name: "",
    display_name: "",
    api_key: "",
    base_url: "",
  });

  const selectedProviderDef = providerDefs.find((p) => p.value === form.provider_name);
  const needsBaseUrl = form.provider_name === "openai_compatible";
  const defaultBaseUrl = selectedProviderDef?.base_url || "";

  // Filtered models for current provider + purpose
  const filteredModels = allModels.filter(
    (m) => m.provider === form.provider_name && m.purpose === form.purpose
  );

  const fetchData = async () => {
    try {
      const [provData, modelData] = await Promise.all([
        api.get<ProviderItem[]>("/v1/admin/providers"),
        api.get<{ providers: ProviderDef[]; models: ModelDef[] }>("/v1/admin/models"),
      ]);
      setProviders(provData);
      setProviderDefs(modelData.providers);
      setAllModels(modelData.models);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  // Auto-select first model when provider/purpose changes
  useEffect(() => {
    if (filteredModels.length > 0 && !filteredModels.find(m => m.model === form.model_name)) {
      const first = filteredModels[0];
      setForm((f) => ({
        ...f,
        model_name: first.model,
        display_name: first.label,
      }));
    }
  }, [form.provider_name, form.purpose, allModels]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/v1/admin/providers", form);
      setShowAdd(false);
      setForm({ provider_name: "openai", purpose: "embedding", model_name: "", display_name: "", api_key: "", base_url: "" });
      fetchData();
    } catch (err: any) {
      setError(err.message || "Failed to add provider");
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteTarget) return;
    await api.delete(`/v1/admin/providers/${deleteTarget}`);
    setDeleteTarget(null);
    fetchData();
  };

  const toggleActive = async (provider: ProviderItem) => {
    try {
      await api.patch(`/v1/admin/providers/${provider.id}`, { is_active: !provider.is_active });
      fetchData();
    } catch (err: any) {
      setError(err.message || "Failed to update provider");
    }
  };

  if (!isSuper) {
    return (
      <div className="flex items-center justify-center h-64">
        <p style={{ color: "var(--muted)" }}>Access denied. Super admin only.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
            Cài đặt AI
          </h2>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
            Nhà cung cấp embedding (lập chỉ mục) và LLM (trả lời). Hỗ trợ OpenAI, Gemini, Anthropic và mọi gateway OpenAI-compatible (OpenRouter, GreenNode MaaS…).
          </p>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white"
          style={{ background: "var(--accent)" }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          Thêm provider
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <form
          onSubmit={handleAdd}
          className="rounded-xl p-5 mb-6"
          style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        >
          {error && (
            <div className="flex items-center gap-2 rounded-lg px-4 py-3 mb-4 text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#ef4444" }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="flex-shrink-0">
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.2" />
                <path d="M8 5V9M8 11V11.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span>{error}</span>
              <button onClick={() => setError("")} className="ml-auto" style={{ color: "#ef4444" }}>✕</button>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Provider selector */}
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Provider</label>
              <select
                value={form.provider_name}
                onChange={(e) => setForm({ ...form, provider_name: e.target.value, model_name: "", base_url: "" })}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              >
                {providerDefs.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            {/* Purpose selector */}
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Purpose</label>
              <select
                value={form.purpose}
                onChange={(e) => setForm({ ...form, purpose: e.target.value, model_name: "" })}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              >
                {PURPOSE_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            {/* Model selector */}
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Model</label>
              <select
                value={form.model_name}
                onChange={(e) => {
                  const model = filteredModels.find((m) => m.model === e.target.value);
                  setForm({ ...form, model_name: e.target.value, display_name: model?.label || e.target.value });
                }}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none"
                style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
              >
                {filteredModels.length === 0 ? (
                  <option value={form.model_name}>{form.model_name || "Nhập tên model ở ô dưới"}</option>
                ) : (
                  filteredModels.map((m) => (
                    <option key={m.model} value={m.model}>
                      {m.label}{m.dimensions ? ` (${m.dimensions}d)` : ""}
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* Base URL (OpenAI-compatible gateways) */}
            {(needsBaseUrl || defaultBaseUrl) && (
              <div className="sm:col-span-2">
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>
                  Base URL {needsBaseUrl ? "(bắt buộc)" : "(mặc định theo provider, có thể ghi đè)"}
                </label>
                <input
                  value={form.base_url}
                  onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                  placeholder={defaultBaseUrl || "https://…/v1"}
                  required={needsBaseUrl}
                  className="w-full rounded-lg px-3 py-2 text-sm outline-none font-mono"
                  style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                />
              </div>
            )}
            {filteredModels.length === 0 && (
              <div className="sm:col-span-2">
                <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>Model ID (tự nhập)</label>
                <input
                  value={form.model_name}
                  onChange={(e) => setForm({ ...form, model_name: e.target.value, display_name: e.target.value })}
                  placeholder="vd. google/gemma-4-31b-it"
                  className="w-full rounded-lg px-3 py-2 text-sm outline-none font-mono"
                  style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                />
              </div>
            )}

            {/* API Key */}
            <div>
              <label className="block text-xs font-medium mb-1" style={{ color: "var(--muted)" }}>API Key</label>
              <input
                type="password" required value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                className="w-full rounded-lg px-3 py-2 text-sm outline-none font-mono"
                style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
                placeholder="sk-... / AIza..."
              />
            </div>
          </div>

          {/* Selected model info */}
          {form.model_name && (
            <div className="mt-3 flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
              <span className="px-2 py-0.5 rounded-full font-medium" style={PURPOSE_COLORS[form.purpose]}>
                {form.purpose.toUpperCase()}
              </span>
              <span className="font-mono">{form.model_name}</span>
              {filteredModels.find((m) => m.model === form.model_name)?.dimensions && (
                <span>• {filteredModels.find((m) => m.model === form.model_name)?.dimensions}d</span>
              )}
            </div>
          )}

          <div className="flex gap-3 mt-4">
            <button
              type="submit"
              disabled={!form.model_name || !form.api_key}
              className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
              style={{ background: "var(--accent)" }}
            >
              Add Provider
            </button>
            <button type="button" onClick={() => setShowAdd(false)} className="rounded-lg px-4 py-2 text-sm" style={{ color: "var(--muted)" }}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Providers list */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : providers.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center rounded-xl py-16"
          style={{ border: "1px dashed var(--border)", background: "var(--card)" }}
        >
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" className="mb-3">
            <path d="M16 20L24 28L32 20" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" />
            <rect x="8" y="8" width="32" height="32" rx="8" stroke="var(--muted)" strokeWidth="1.5" strokeDasharray="4 3" />
          </svg>
          <p className="text-sm" style={{ color: "var(--muted)" }}>No AI providers configured</p>
          <p className="text-xs mt-1" style={{ color: "var(--muted)", opacity: 0.7 }}>Add a provider to enable document indexing</p>
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
          {providers.map((p) => {
            const purposeStyle = PURPOSE_COLORS[p.purpose] || PURPOSE_COLORS.embedding;
            return (
              <div
                key={p.id}
                className="rounded-xl p-5 transition-all duration-200"
                style={{
                  background: "var(--card)",
                  border: p.is_active ? "1px solid var(--accent)" : "1px solid var(--border)",
                  opacity: p.is_active ? 1 : 0.6,
                }}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-semibold truncate" style={{ color: "var(--foreground)" }}>{p.display_name}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0" style={purposeStyle}>
                      {p.purpose.toUpperCase()}
                    </span>
                    {p.is_active && (
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0" style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e" }}>
                        Active
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => toggleActive(p)}
                      className="rounded-lg p-1.5 text-xs transition-colors"
                      style={{ color: "var(--muted)" }}
                      title={p.is_active ? "Deactivate" : "Activate"}
                    >
                      {p.is_active ? "⏸" : "▶"}
                    </button>
                    <button
                      onClick={() => setDeleteTarget(p.id)}
                      className="rounded-lg p-1.5 transition-colors"
                      style={{ color: "var(--muted)" }}
                      onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; }}
                    >
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M3 3L11 11M3 11L11 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    </button>
                  </div>
                </div>
                <div className="flex flex-col gap-1 text-xs" style={{ color: "var(--muted)" }}>
                  <div className="flex items-center gap-2">
                    <span>Provider:</span>
                    <span className="font-mono px-1.5 py-0.5 rounded" style={{ background: "var(--background)" }}>{p.provider_name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span>Model:</span>
                    <span className="font-mono px-1.5 py-0.5 rounded" style={{ background: "var(--background)" }}>{p.model_name}</span>
                  </div>
                  {p.base_url && (
                    <div className="flex items-center gap-2 min-w-0">
                      <span>URL:</span>
                      <span className="font-mono px-1.5 py-0.5 rounded truncate" style={{ background: "var(--background)" }}>{p.base_url}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-2">
                    <span>Key:</span>
                    <span className="font-mono px-1.5 py-0.5 rounded" style={{ background: "var(--background)" }}>{p.api_key_masked}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        message="Are you sure you want to remove this AI provider?"
        variant="danger"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
