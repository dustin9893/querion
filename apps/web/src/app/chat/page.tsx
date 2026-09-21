"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useI18n } from "@/components/providers/I18nProvider";
import { useWorkspace } from "@/components/providers/AuthProvider";
import { listApps, type AppResponse } from "@/lib/api/apps";
import { apiAssetUrl } from "@/lib/api";
import { adminTransport } from "@/lib/chat/adminTransport";
import { assetUrl, type WidgetConfig } from "@/lib/chat/transport";
import AssistantChat from "@/components/chat/AssistantChat";
import { BRAND_NAME } from "@/lib/brand";

/**
 * "Thử nghiệm hỏi đáp" — the admin test console. Pick an assistant of the active unit and
 * talk to it through the same chat UI, answer pipeline and guardrails as staff/customers.
 * Answers are audited with channel `admin_test` (see routers/app_test.py).
 */

/** Mirror of services/embed.py:effective_widget so the console looks like the real widget. */
function widgetOf(app: AppResponse): WidgetConfig {
  const w = app.widget_config || {};
  return {
    title: w.title || app.name,
    subtitle: w.subtitle ?? app.description ?? "Trả lời từ tài liệu chính thức",
    greeting: w.greeting ?? null,
    primary_color: w.primary_color || (app.audience === "customer" ? "#ee6d1f" : "#1f3a5f"),
    position: "right",
    launcher_text: null,
    suggestions: w.suggestions || [],
    show_powered_by: false,
    theme: w.theme || "light",
    disclaimer: w.disclaimer ?? null,
  };
}

export default function ChatPage() {
  const { t } = useI18n();
  const { activeWorkspace } = useWorkspace();
  const wsId = activeWorkspace?.workspace_id || null;

  const [apps, setApps] = useState<AppResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!wsId) { setApps([]); setLoading(false); return; }
    setLoading(true); setError(null);
    try {
      const list = await listApps();
      setApps(list);
      setSelectedId((cur) => (cur && list.some((a) => a.id === cur) ? cur : null));
    } catch (e: any) {
      setError(e.message || "Không tải được danh sách trợ lý");
    } finally { setLoading(false); }
  }, [wsId]);

  useEffect(() => { load(); }, [load]);

  const selected = useMemo(() => apps.find((a) => a.id === selectedId) || null, [apps, selectedId]);
  const transport = useMemo(() => (selected ? adminTransport(selected.id) : null), [selected]);

  const modeLabel = (a: AppResponse) =>
    a.workflow_id ? t("modeWorkflow", "chat") : a.dataset_ids?.length ? t("modeRag", "chat") : t("modeLlm", "chat");

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>{t("title", "chat")}</h2>
        <p className="text-sm mt-1 max-w-3xl" style={{ color: "var(--muted)" }}>{t("description", "chat")}</p>
      </div>

      <div className="grid gap-4 flex-1 min-h-0" style={{ gridTemplateColumns: "minmax(240px, 300px) 1fr" }}>
        {/* ---- assistants of the active unit ---- */}
        <aside className="rounded-xl p-3 overflow-y-auto" style={{ background: "var(--card)", border: "1px solid var(--border)" }}
          data-testid="admin-test-apps">
          <p className="text-[11px] font-bold uppercase tracking-wider px-1 mb-2" style={{ color: "var(--muted)" }}>{t("assistants", "chat")}</p>
          {loading && <p className="text-xs px-1" style={{ color: "var(--muted)" }}>…</p>}
          {error && <p className="text-xs px-1" style={{ color: "#ef4444" }}>{error}</p>}
          {!loading && !error && apps.length === 0 && (
            <div className="px-1 text-xs space-y-2" style={{ color: "var(--muted)" }}>
              <p>{t("noAssistants", "chat")}</p>
              <Link href="/apps" className="inline-block rounded-lg px-3 py-1.5 font-medium text-white" style={{ background: "var(--accent)" }}>
                {t("createAssistant", "chat")}
              </Link>
            </div>
          )}
          <div className="space-y-1">
            {apps.map((a) => {
              const active = a.id === selectedId;
              const isCustomer = a.audience === "customer";
              const logo = apiAssetUrl(a.logo_url);
              return (
                <button key={a.id} type="button" onClick={() => setSelectedId(a.id)}
                  className="w-full text-left rounded-lg px-2.5 py-2 transition-all"
                  style={{ background: active ? "var(--accent-glow)" : "transparent", border: `1px solid ${active ? "var(--accent)" : "transparent"}` }}>
                  <div className="flex items-center gap-2.5 min-w-0">
                    {logo ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={logo} alt="" className="rounded-lg shrink-0" style={{ width: 28, height: 28, objectFit: "cover" }} />
                    ) : (
                      <div className="rounded-lg shrink-0 flex items-center justify-center" style={{ width: 28, height: 28, background: isCustomer ? "rgba(34,197,94,0.12)" : "var(--accent-glow)" }}>
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: isCustomer ? "#16a34a" : "var(--accent)" }}>
                          <path d="M3 4.5H13M3 8H10M3 11.5H8" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
                        </svg>
                      </div>
                    )}
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate" style={{ color: "var(--foreground)" }}>{a.name}</p>
                      <p className="text-[10px] truncate" style={{ color: "var(--muted)" }}>
                        {isCustomer ? t("audienceCustomer", "chat") : t("audienceStaff", "chat")} · {modeLabel(a)} · {a.is_published ? t("published", "chat") : t("unpublished", "chat")}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* ---- console ---- */}
        <section className="rounded-xl overflow-hidden flex flex-col min-h-0" data-testid="admin-test-console"
          style={{ background: "var(--card)", border: "1px solid var(--border)", minHeight: 560 }}>
          {!selected || !transport ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
              <div className="flex items-center justify-center rounded-full mb-4" style={{ width: 64, height: 64, background: "var(--accent-glow)" }}>
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                  <path d="M5 5H23C23.5523 5 24 5.44772 24 6V20C24 20.5523 23.5523 21 23 21H10L5 26V6C5 5.44772 5.44772 5 6 5H5Z" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M10 11H18" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
                  <path d="M10 15H14" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <p className="text-sm font-medium" style={{ color: "var(--muted)" }}>{t("selectAssistant", "chat")}</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between gap-3 px-4 py-2 text-xs" style={{ borderBottom: "1px solid var(--border)", color: "var(--muted)" }}>
                <span className="truncate">{t("testingNote", "chat")}</span>
                <Link href={`/apps/${selected.id}`} className="shrink-0 rounded-lg px-2.5 py-1 font-medium" style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                  {t("openSettings", "chat")}
                </Link>
              </div>
              <div className="flex-1 min-h-0" style={{ background: "#f7f7f9" }}>
                <AssistantChat
                  key={selected.id}
                  transport={transport}
                  widget={widgetOf(selected)}
                  logoUrl={assetUrl(selected.logo_url)}
                  variant="embed"
                  brandName={BRAND_NAME}
                  storageKey={`querion-admin-test-${selected.id}`}
                  askReasonOnDown
                />
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
