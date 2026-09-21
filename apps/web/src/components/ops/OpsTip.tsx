"use client";

/**
 * Lời mời nhỏ bật lên cạnh bong bóng vận hành: **"Cần trợ giúp?"**.
 *
 * Khi có một gợi ý hợp với trang đang mở thì nó kèm thêm một câu gợi ý cụ thể; không có thì chỉ
 * là lời mời gọn. Nhờ vậy bong bóng vẫn nhắc người ta nhớ tới nó ở mọi trang, mà lúc nào có điều
 * đáng nói thì nói luôn.
 *
 * Về animation: bản đầu chờ 25 giây rồi trượt lên trong 0,26 giây. Kỹ thuật thì chạy đúng, nhưng
 * thực tế không ai kịp thấy — mắt không nhìn vào góc đó đúng khoảnh khắc ấy. Nay lời mời bung ra
 * từ chính nút bấm trong 0,42 giây, chữ hiện so le theo sau, và nút bấm lắc nhẹ một nhịp để kéo
 * mắt về phía đó. Lần đầu chỉ chờ 6 giây, đủ để trang vẽ xong chứ không lâu tới mức quên.
 *
 * Đây vẫn là thứ dễ gây phiền nhất trong cả tính năng, nên trần là **trần cứng**: hết số lần mỗi
 * phiên là thôi. Người dùng tắt hẳn được cho riêng mình, super admin tắt được cho cả hệ thống.
 *
 * Trạng thái "đã xem" nằm trong localStorage, tức theo từng trình duyệt. Mất cũng không sao: hậu
 * quả xấu nhất là một gợi ý hiện lại, nên không đáng tốn một bảng trong cơ sở dữ liệu.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { OpsTip as Tip } from "@/lib/api/ops";

const SEEN_KEY = "msbka-ops-tips-seen";
const OFF_KEY = "msbka-ops-tips-off";
const FIRST_DELAY_MS = 6_000;
const VISIBLE_MS = 11_000;
const HEADLINE = "Cần trợ giúp?";

function readSeen(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]") as string[]);
  } catch {
    return new Set();
  }
}
function remember(id: string) {
  try {
    const seen = readSeen();
    seen.add(id);
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-200)));
  } catch { /* riêng tư hoặc bị chặn: coi như chưa xem, cùng lắm hiện lại */ }
}
export function tipsMuted(): boolean {
  try { return localStorage.getItem(OFF_KEY) === "1"; } catch { return false; }
}
function mute() {
  try { localStorage.setItem(OFF_KEY, "1"); } catch { /* ignore */ }
}

interface Props {
  tips: Tip[];
  route: string;
  /** không bao giờ hiện khi panel đang mở */
  paused: boolean;
  intervalSec: number;
  maxPerSession: number;
  accent: string;
  onAsk: (question: string | null) => void;
  /** báo cho bong bóng biết để lắc nhẹ nút bấm cùng lúc lời mời bung ra */
  onNudge?: (showing: boolean) => void;
}

export default function OpsTip({
  tips, route, paused, intervalSec, maxPerSession, accent, onAsk, onNudge,
}: Props) {
  /** `{tip: null}` là lời mời trơn, không kèm gợi ý nào */
  const [current, setCurrent] = useState<{ tip: Tip | null } | null>(null);
  const shown = useRef(0);
  const muted = useRef(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Giữ callback trong ref để effect hẹn giờ không phải chạy lại mỗi lần cha vẽ lại.
  // Gán trong effect chứ không gán lúc render: ghi vào ref khi đang render là sai luật React.
  const notify = useRef(onNudge);
  useEffect(() => { notify.current = onNudge; }, [onNudge]);

  useEffect(() => { muted.current = tipsMuted(); }, []);

  const pick = useCallback((): Tip | null => {
    const seen = readSeen();
    const fresh = tips.filter((t) => !seen.has(t.id));
    // Ưu tiên gợi ý gắn với đúng trang đang mở: đó là lúc nó hữu ích chứ không phải quảng cáo.
    return fresh.find((t) => t.route && route.startsWith(t.route)) || fresh.find((t) => !t.route) || null;
  }, [tips, route]);

  useEffect(() => {
    if (paused || muted.current || maxPerSession <= 0) return;
    const delay = shown.current === 0 ? FIRST_DELAY_MS : Math.max(intervalSec, 60) * 1000;
    const timer = setTimeout(() => {
      if (shown.current >= maxPerSession) return;
      shown.current += 1;
      setCurrent({ tip: pick() });
      notify.current?.(true);
      hideTimer.current = setTimeout(() => { setCurrent(null); notify.current?.(false); }, VISIBLE_MS);
    }, delay);
    return () => clearTimeout(timer);
    // `current` ở deps để sau khi một lời mời biến mất thì hẹn giờ cho lần kế tiếp
  }, [paused, intervalSec, maxPerSession, pick, current]);

  useEffect(() => () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    notify.current?.(false);
  }, []);

  if (!current) return null;
  const tip = current.tip;

  const close = () => { setCurrent(null); notify.current?.(false); };
  const dismiss = () => { if (tip) remember(tip.id); close(); };
  const ask = () => {
    if (tip) remember(tip.id);
    close();
    onAsk(tip?.ask || null);
  };

  return (
    <button data-testid="ops-tip" onClick={ask}
            className="msbka-tip pointer-events-auto mb-2 w-[min(19rem,calc(100vw-3rem))] rounded-2xl p-3 text-left shadow-xl"
            style={{ background: "var(--card, #fff)", border: `1px solid ${accent}` }}>
      <span className="msbka-line msbka-l1 flex items-center gap-2">
        <span aria-hidden className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-white"
              style={{ background: accent }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M4 13v-1a8 8 0 0116 0v1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            <path d="M3 14.5h3v5H4.5A1.5 1.5 0 013 18v-3.5zM21 14.5h-3v5h1.5A1.5 1.5 0 0021 18v-3.5z"
                  stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="text-[13px] font-semibold" style={{ color: "var(--foreground, #0f172a)" }}>
          {HEADLINE}
        </span>
        <span role="button" tabIndex={0} aria-label="Đừng nhắc nữa"
              onClick={(e) => { e.stopPropagation(); mute(); muted.current = true; close(); }}
              onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); mute(); muted.current = true; close(); } }}
              className="ml-auto text-[11px] opacity-60 hover:opacity-100"
              style={{ color: "var(--muted, #64748b)" }}>Đừng nhắc nữa</span>
      </span>

      {tip && (
        <span className="msbka-line msbka-l2 mt-1.5 block text-[12px] leading-snug"
              style={{ color: "var(--muted, #64748b)" }}>
          {tip.text}
        </span>
      )}

      <span className="msbka-line msbka-l3 mt-2 flex items-center gap-2">
        <span className="rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white" style={{ background: accent }}>
          {tip?.ask ? "Hỏi thêm" : "Mở trợ lý"}
        </span>
        <span role="button" tabIndex={0}
              onClick={(e) => { e.stopPropagation(); dismiss(); }}
              onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); dismiss(); } }}
              className="text-[11px] opacity-70 hover:opacity-100" style={{ color: "var(--muted, #64748b)" }}>Ẩn</span>
      </span>

      <style jsx>{`
        /* Bung ra từ phía nút bấm, hơi quá đà một chút rồi về chỗ, nên mắt bắt được chuyển động. */
        .msbka-tip {
          transform-origin: bottom right;
          animation: msbka-tip-pop 420ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
        }
        /* Chữ hiện so le sau khung, để người đọc thấy nội dung "chạy vào" chứ không bật cái rụp. */
        .msbka-line { animation: msbka-line-in 280ms ease-out both; }
        .msbka-l1 { animation-delay: 110ms; }
        .msbka-l2 { animation-delay: 190ms; }
        .msbka-l3 { animation-delay: 260ms; }

        @keyframes msbka-tip-pop {
          0% { opacity: 0; transform: translate(14px, 14px) scale(0.6); }
          100% { opacity: 1; transform: translate(0, 0) scale(1); }
        }
        @keyframes msbka-line-in {
          0% { opacity: 0; transform: translateY(6px); }
          100% { opacity: 1; transform: translateY(0); }
        }
        @media (prefers-reduced-motion: reduce) {
          .msbka-tip, .msbka-line { animation: none; }
        }
      `}</style>
    </button>
  );
}
