"use client";

/**
 * Bản nháp luồng xử lý trợ lý vừa soạn, hiện ngay dưới câu trả lời.
 *
 * Trợ lý **không lưu gì cả**. Thẻ này là chỗ người dùng bấm, và nút bấm gọi API tạo luồng bằng
 * chính quyền của họ trong đơn vị họ đang mở. Nhờ vậy không có đường ghi mới nào cho AI, và
 * không cần cơ chế duyệt thao tác: quyền đúng bằng quyền người đang ngồi trước màn hình.
 */
import { useState } from "react";
import type { WorkflowDraft } from "@/lib/api/ops";
import { createWorkflow, updateWorkflow } from "@/lib/api/workflows";
import type { GraphJSON } from "@/lib/api/workflows";

interface Props {
  draft: WorkflowDraft;
  accent: string;
  muted: string;
  text: string;
  border: string;
  accentLight: string;
}

export default function WorkflowDraftCard({ draft, accent, muted, text, border, accentLight }: Props) {
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [error, setError] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);

  const nodes = draft.graph_json?.nodes || [];
  const steps = nodes.filter((n) => n.type !== "input" && n.type !== "output");
  const isEdit = Boolean(draft.workflow_id);

  const apply = async () => {
    setState("saving");
    setError("");
    try {
      let id = draft.workflow_id;
      if (id) {
        await updateWorkflow(id, { graph_json: draft.graph_json as unknown as GraphJSON });
      } else {
        const created = await createWorkflow(draft.ten, "chatflow", draft.mo_ta);
        id = created.id;
        await updateWorkflow(id, { graph_json: draft.graph_json as unknown as GraphJSON });
      }
      setSavedId(id);
      setState("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tạo được luồng");
      setState("error");
    }
  };

  return (
    <div className="mt-2.5 rounded-xl p-3" data-testid="workflow-draft"
         style={{ background: accentLight, border: `1px solid ${accent}` }}>
      <div className="flex items-start gap-2">
        <span aria-hidden className="text-base leading-none">🧩</span>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold" style={{ color: text }}>
            {isEdit ? `Sửa luồng: ${draft.workflow_name || draft.ten}` : draft.ten}
          </div>
          <div className="text-[11px]" style={{ color: muted }}>
            {steps.length} bước · bản nháp, chưa lưu
          </div>
        </div>
      </div>

      <ol className="mt-2 space-y-1">
        {steps.map((n, i) => (
          <li key={n.id} className="flex items-baseline gap-1.5 text-[11px]" style={{ color: muted }}>
            <span className="shrink-0 font-mono" style={{ color: accent }}>{i + 1}.</span>
            <span className="truncate" style={{ color: text }}>{n.data?.label || n.type}</span>
            <span className="shrink-0 font-mono opacity-60">{n.type}</span>
          </li>
        ))}
      </ol>

      {state === "done" && savedId ? (
        <div className="mt-2.5 flex items-center gap-2">
          <span className="text-[11px]" style={{ color: muted }}>Đã tạo.</span>
          <a href={`/workflows/${savedId}`} target="_blank" rel="noreferrer"
             className="rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white"
             style={{ background: accent }}>Mở trên canvas</a>
        </div>
      ) : (
        <div className="mt-2.5 flex items-center gap-2">
          <button onClick={apply} disabled={state === "saving"} data-testid="workflow-draft-apply"
                  className="rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-60"
                  style={{ background: accent }}>
            {state === "saving" ? "Đang tạo…" : isEdit ? "Cập nhật luồng" : "Tạo luồng"}
          </button>
          <span className="text-[11px]" style={{ color: muted }}>
            Kiểm lại trên canvas rồi hãy dùng thật.
          </span>
        </div>
      )}
      {state === "error" && (
        <div className="mt-1.5 text-[11px]" style={{ color: "#dc2626", borderTop: `1px solid ${border}` }}>{error}</div>
      )}
    </div>
  );
}
