"use client";

/**
 * Bong bóng Trợ lý Vận hành, gắn một lần trong `AppShell` nên có mặt ở mọi trang quản trị.
 *
 * Tự ẩn ở những nơi nó thừa hoặc vướng:
 *   - `/login`, `/staff`, `/kh`, `/embed` — `AppShell` vốn đã không dựng vỏ quản trị ở đó
 *   - `/chat` — màn hình thử nghiệm hỏi đáp đã là một khung chat toàn trang, hai khung cạnh nhau
 *     chỉ gây rối. Cùng lý do khiến extension tự tắt trên trang đã nhúng widget.
 *
 * Khung chat dùng lại `AssistantChat` như cổng cán bộ, trang khách hàng và extension, nên trích
 * dẫn, chip công cụ và 👍/👎 hành xử giống hệt nhau mà không phải viết lại.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";

import AssistantChat, { type UiMessage } from "@/components/chat/AssistantChat";
import OpsTip from "@/components/ops/OpsTip";
import WorkflowDraftCard from "@/components/ops/WorkflowDraftCard";
import { getOpsBubble, type OpsBubble as BubbleConfig, type WorkflowDraft } from "@/lib/api/ops";
import { opsTransport } from "@/lib/chat/opsTransport";

const HIDDEN_PREFIXES = ["/login", "/staff", "/kh", "/embed", "/chat"];
// Hội thoại được nhớ lại; trạng thái mở/đóng thì không, vì AppShell sống suốt phiên làm việc.
const STORAGE_KEY = "msbka-ops-conversation";

export default function OpsBubble() {
  const pathname = usePathname() || "/";
  const [cfg, setCfg] = useState<BubbleConfig | null>(null);
  const [open, setOpen] = useState(false);
  const [prefill, setPrefill] = useState<string | null>(null);
  /** nút bấm lắc một nhịp đúng lúc lời mời bung ra, để mắt bắt được chuyển động ở góc màn hình */
  const [nudging, setNudging] = useState(false);

  const hidden = HIDDEN_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"));

  useEffect(() => {
    if (hidden) return;
    let alive = true;
    getOpsBubble()
      .then((c) => { if (alive) setCfg(c); })
      .catch(() => { if (alive) setCfg({ enabled: false }); });
    return () => { alive = false; };
  }, [hidden]);

  // Esc đóng panel, giống mọi lớp phủ khác trong sản phẩm
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const transport = useMemo(() => opsTransport(), []);
  const accent = cfg?.primary_color || "#ee6d1f";

  const widget = useMemo(() => ({
    title: cfg?.name || "Trợ lý Vận hành",
    subtitle: "Hỗ trợ quản trị hệ thống",
    greeting: cfg?.greeting || "",
    primary_color: accent,
    suggestions: cfg?.suggestions || [],
    show_powered_by: false,
    disclaimer: "Trợ lý chỉ hướng dẫn và soạn nháp. Mọi thay đổi vẫn do anh/chị bấm nút.",
    position: "right" as const,
    theme: "auto" as const,
  }), [cfg, accent]);

  const askFromTip = useCallback((question: string | null) => {
    if (question) setPrefill(question);
    setOpen(true);
  }, []);

  const renderExtra = useCallback((m: UiMessage) => {
    const drafts = (m.drafts || []) as WorkflowDraft[];
    if (!drafts.length) return null;
    return (
      <>
        {drafts.map((d, i) => (
          <WorkflowDraftCard key={`${d.ten}-${i}`} draft={d} accent={accent}
                             muted="#64748b" text="#0f172a" border="rgba(15,23,42,0.08)"
                             accentLight="rgba(238,109,31,0.10)" />
        ))}
      </>
    );
  }, [accent]);

  if (hidden || !cfg?.enabled) return null;

  return (
    <div className="fixed bottom-5 right-5 z-[60] flex flex-col items-end" data-testid="ops-bubble-root">
      {!open && (
        <OpsTip tips={cfg.tips || []} route={pathname} paused={open}
                intervalSec={cfg.tip_interval_sec ?? 300}
                maxPerSession={cfg.max_tips_per_session ?? 3}
                accent={accent} onAsk={askFromTip} onNudge={setNudging} />
      )}

      {open && (
        <div data-testid="ops-panel"
             className="msbka-ops-panel mb-3 overflow-hidden rounded-2xl shadow-2xl"
             style={{ width: "min(24rem, calc(100vw - 2.5rem))", height: "min(34rem, calc(100vh - 7rem))" }}>
          <AssistantChat
            transport={transport}
            widget={widget}
            variant="embed"
            storageKey={STORAGE_KEY}
            brandName="MSB Knowledge Assistant"
            askReasonOnDown
            logoUrl={null}
            prefill={prefill}
            showSources={false}
            onClose={() => setOpen(false)}
            renderExtra={renderExtra}
          />
        </div>
      )}

      <button onClick={() => setOpen((v) => !v)} data-testid="ops-bubble"
              aria-label={open ? "Đóng trợ lý vận hành" : "Mở trợ lý vận hành"}
              title={open ? "Đóng trợ lý vận hành" : "Cần trợ giúp?"}
              className={`msbka-ops-launcher relative flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg transition-transform hover:scale-105${nudging && !open ? " msbka-nudge" : ""}`}
              style={{ background: accent }}>
        {nudging && !open && (
          <span aria-hidden className="msbka-ring absolute inset-0 rounded-2xl"
                style={{ border: `2px solid ${accent}` }} />
        )}
        {open ? (
          <svg width="22" height="22" viewBox="0 0 20 20" fill="none" aria-hidden>
            <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        ) : (
          /* tai nghe tổng đài: quen thuộc với "hỗ trợ", không nhầm sang biểu tượng bảo mật */
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path d="M4 13.5v-1.5a8 8 0 0116 0v1.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
            <path d="M2.6 14.2h3.2v5.6H4.4a1.8 1.8 0 01-1.8-1.8v-3.8zM21.4 14.2h-3.2v5.6h1.4a1.8 1.8 0 001.8-1.8v-3.8z"
                  stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            <path d="M19.4 19.8v.4a2.4 2.4 0 01-2.4 2.4h-3.6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        )}
      </button>

      <style jsx>{`
        .msbka-ops-panel { animation: msbka-panel-in 180ms ease-out; }
        /* Lắc nhẹ một nhịp, không lặp: đủ để kéo mắt, không thành đèn nhấp nháy. */
        .msbka-nudge { animation: msbka-wiggle 620ms ease-in-out 1; }
        .msbka-ring { animation: msbka-ring-out 1100ms ease-out 2; }

        @keyframes msbka-panel-in {
          from { opacity: 0; transform: translateY(12px) scale(0.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes msbka-wiggle {
          0%, 100% { transform: rotate(0) scale(1); }
          20% { transform: rotate(-7deg) scale(1.06); }
          45% { transform: rotate(6deg) scale(1.06); }
          70% { transform: rotate(-3deg) scale(1.03); }
        }
        @keyframes msbka-ring-out {
          0% { opacity: 0.55; transform: scale(1); }
          100% { opacity: 0; transform: scale(1.6); }
        }
        @media (prefers-reduced-motion: reduce) {
          .msbka-ops-panel, .msbka-nudge, .msbka-ring { animation: none; }
          .msbka-ops-launcher { transition: none; }
        }
      `}</style>
    </div>
  );
}
