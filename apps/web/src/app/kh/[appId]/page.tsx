"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { BRAND_NAME } from "@/lib/brand";
import AssistantChat from "@/components/chat/AssistantChat";
import { customerTransport, type WidgetConfig, assetUrl } from "@/lib/chat/transport";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AssistantInfo { id: string; name: string; description: string | null;   logo_url?: string | null;
}

const PAGE_SUGGESTIONS = [
  "Phí chuyển khoản liên ngân hàng trên app là bao nhiêu?",
  "Vay mua nhà được vay tối đa bao nhiêu phần trăm giá trị nhà?",
  "Tôi quên mật khẩu đăng nhập ứng dụng thì làm thế nào?",
  "Trả nợ trước hạn có mất phí không?",
];

/**
 * Full-page customer assistant: /kh/<appId>#k=<api_key>
 * Same chat engine as the embedded widget (AssistantChat + customerTransport).
 */
export default function CustomerAssistantPage() {
  const params = useParams();
  const search = useSearchParams();
  const appId = params.appId as string;

  // Prefer #k=… (fragment is not sent to the server); accept ?k=… for backwards compatibility.
  const [apiKey, setApiKey] = useState<string>("");
  useEffect(() => {
    const read = () => {
      const fromHash = window.location.hash.match(/[#&]k=([^&]+)/)?.[1];
      setApiKey(fromHash ? decodeURIComponent(fromHash) : (search.get("k") || "missing"));
    };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, [search]);

  const [info, setInfo] = useState<AssistantInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInfo(null); setError(null);
    if (apiKey === "") return;
    if (apiKey === "missing") { setError("Thiếu mã truy cập trợ lý (link không hợp lệ)."); return; }
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/v1/public/assistants/${appId}`, { headers: { "X-App-Key": apiKey } });
        if (!res.ok) throw new Error("Trợ lý không tồn tại hoặc chưa được công bố.");
        setInfo(await res.json());
      } catch (e: any) {
        setError(e.message || "Không tải được trợ lý.");
      }
    })();
  }, [appId, apiKey]);

  const transport = useMemo(() => customerTransport(appId, apiKey), [appId, apiKey]);
  const widget: WidgetConfig | null = useMemo(() => info ? ({
    title: info.name,
    subtitle: info.description,
    greeting: `Xin chào! Tôi là ${info.name}. Tôi có thể giải đáp về sản phẩm, biểu phí, thủ tục và câu hỏi thường gặp dựa trên tài liệu chính thức. Câu trả lời luôn kèm nguồn trích dẫn.`,
    primary_color: "#ee6d1f", position: "right", launcher_text: null,
    suggestions: PAGE_SUGGESTIONS, show_powered_by: false, theme: "light", disclaimer: null,
  }) : null, [info]);

  if (error) {
    return (
      <div style={{ minHeight: "100vh", background: "#f7f7f9", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div className="rounded-xl p-6 text-center text-sm" style={{ background: "#fff", border: "1px solid rgba(15,23,42,0.08)", maxWidth: 420 }}>
          <p className="font-semibold mb-1">Không thể mở trợ lý</p>
          <p style={{ color: "#64748b" }}>{error}</p>
        </div>
      </div>
    );
  }
  if (!info || !widget) {
    return <div style={{ minHeight: "100vh", background: "#f7f7f9" }} />;
  }
  return (
    <AssistantChat transport={transport} widget={widget} logoUrl={assetUrl(info.logo_url)} variant="page" brandName={BRAND_NAME}
      storageKey={`querion-kh-conv-${appId}`} />
  );
}
