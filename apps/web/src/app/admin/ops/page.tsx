"use client";

/**
 * Cấu hình Trợ lý Vận hành — chỉ super admin.
 *
 * Một màn hình, một nút lưu, tuy phía sau ghi vào hai bảng: `ops_config` giữ các nút bấm của
 * bong bóng, còn dòng `apps` giữ bản thân trợ lý. Người dùng không cần biết chuyện đó.
 */
import { useEffect, useState } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { getOpsConfig, saveOpsConfig, type OpsConfig, type OpsTip } from "@/lib/api/ops";

const ROLE_LABELS: Record<string, string> = {
  admin: "Quản trị đơn vị",
  super_admin: "Quản trị hệ thống",
};

function Card({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl p-5" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
      <h2 className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>{title}</h2>
      {hint && <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{hint}</p>}
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium" style={{ color: "var(--foreground)" }}>{label}</span>
      {hint && <span className="ml-2 text-[11px]" style={{ color: "var(--muted)" }}>{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

const inputStyle = {
  background: "var(--background)",
  border: "1px solid var(--border)",
  color: "var(--foreground)",
};

export default function OpsAdminPage() {
  const { isSuper } = useAuth();
  const [cfg, setCfg] = useState<OpsConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!isSuper) { setLoading(false); return; }
    getOpsConfig()
      .then(setCfg)
      .catch((e) => setError(e instanceof Error ? e.message : "Không đọc được cấu hình"))
      .finally(() => setLoading(false));
  }, [isSuper]);

  if (!isSuper) {
    return <p className="text-sm" style={{ color: "var(--muted)" }}>Chỉ quản trị hệ thống mới cấu hình được trợ lý vận hành.</p>;
  }
  if (loading) return <p className="text-sm" style={{ color: "var(--muted)" }}>Đang tải…</p>;
  if (!cfg) return <p className="text-sm text-red-600">{error || "Không đọc được cấu hình"}</p>;

  const patch = (p: Partial<OpsConfig>) => setCfg({ ...cfg, ...p } as OpsConfig);
  const patchTip = (i: number, p: Partial<OpsTip>) =>
    patch({ tips: cfg.tips.map((t, j) => (j === i ? { ...t, ...p } : t)) });

  const save = async () => {
    setSaving(true); setError(""); setSaved(false);
    try {
      const next = await saveOpsConfig({
        enabled: cfg.enabled,
        audience_roles: cfg.audience_roles,
        tips: cfg.tips,
        tip_interval_sec: cfg.tip_interval_sec,
        max_tips_per_session: cfg.max_tips_per_session,
        workflow_gen_enabled: cfg.workflow_gen_enabled,
        system_prompt: cfg.assistant?.system_prompt,
        model: cfg.assistant?.model,
        greeting: cfg.assistant?.greeting,
      });
      setCfg(next);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không lưu được");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5 pb-24">
      <header>
        <h1 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>Trợ lý Vận hành</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          Bong bóng hỗ trợ quản trị viên, hiện ở góc mọi trang quản trị. Trợ lý chỉ hướng dẫn và
          soạn nháp; nó không tự thay đổi cấu hình của hệ thống.
        </p>
      </header>

      <Card title="Hiển thị">
        <label className="flex items-center gap-2 text-sm" style={{ color: "var(--foreground)" }}>
          <input type="checkbox" checked={cfg.enabled} onChange={(e) => patch({ enabled: e.target.checked })} />
          Bật bong bóng trợ lý vận hành
        </label>
        <Row label="Ai nhìn thấy" hint="tắt hết là không ai thấy">
          <div className="flex gap-4">
            {Object.entries(ROLE_LABELS).map(([value, label]) => (
              <label key={value} className="flex items-center gap-2 text-sm" style={{ color: "var(--foreground)" }}>
                <input type="checkbox" checked={cfg.audience_roles.includes(value)}
                       onChange={(e) => patch({
                         audience_roles: e.target.checked
                           ? [...cfg.audience_roles, value]
                           : cfg.audience_roles.filter((r) => r !== value),
                       })} />
                {label}
              </label>
            ))}
          </div>
        </Row>
      </Card>

      <Card title="Trợ lý"
            hint={cfg.assistant ? `Trợ lý hệ thống id ${cfg.assistant.id}` : "Chưa seed trợ lý. Chạy python -m app.seed_ops."}>
        {cfg.assistant && (
          <>
            <Row label="Model" hint="để trống thì dùng model đang bật trong Cài đặt AI">
              <input value={cfg.assistant.model} style={inputStyle}
                     onChange={(e) => patch({ assistant: { ...cfg.assistant!, model: e.target.value } })}
                     className="w-full rounded-lg px-3 py-2 text-sm font-mono" placeholder="z-ai/glm-5.2-hackathon" />
            </Row>
            <p className="-mt-2 text-[11px]" style={{ color: "var(--muted)" }}>
              Soạn luồng xử lý là việc xuất JSON có cấu trúc, model hội thoại hằng ngày làm không
              đạt. Đổi model ở đây chỉ ảnh hưởng trợ lý này.
            </p>
            <Row label="Lời chào">
              <input value={cfg.assistant.greeting} style={inputStyle}
                     onChange={(e) => patch({ assistant: { ...cfg.assistant!, greeting: e.target.value } })}
                     className="w-full rounded-lg px-3 py-2 text-sm" />
            </Row>
            <Row label="System prompt" hint="quy tắc trả lời, đổi thì cân nhắc kỹ">
              <textarea value={cfg.assistant.system_prompt} rows={8} style={inputStyle}
                        onChange={(e) => patch({ assistant: { ...cfg.assistant!, system_prompt: e.target.value } })}
                        className="w-full rounded-lg px-3 py-2 font-mono text-xs" />
            </Row>
          </>
        )}
      </Card>

      <Card title="Soạn luồng xử lý"
            hint="Trợ lý dựng bản nháp từ mô tả tiếng Việt. Bản nháp không được lưu; người dùng phải tự bấm nút tạo.">
        <label className="flex items-center gap-2 text-sm" style={{ color: "var(--foreground)" }}>
          <input type="checkbox" checked={cfg.workflow_gen_enabled}
                 onChange={(e) => patch({ workflow_gen_enabled: e.target.checked })} />
          Cho phép trợ lý soạn và sửa luồng xử lý
        </label>
      </Card>

      <Card title="Gợi ý tự bật"
            hint="Hiện cạnh bong bóng khi người dùng đang ở đúng trang. Trần cứng theo phiên làm việc để không gây phiền.">
        <div className="grid grid-cols-2 gap-4">
          <Row label="Khoảng cách hai gợi ý (giây)" hint="tối thiểu 60">
            <input type="number" min={60} value={cfg.tip_interval_sec} style={inputStyle}
                   onChange={(e) => patch({ tip_interval_sec: Number(e.target.value) })}
                   className="w-full rounded-lg px-3 py-2 text-sm" />
          </Row>
          <Row label="Tối đa mỗi phiên" hint="0 là tắt gợi ý">
            <input type="number" min={0} max={10} value={cfg.max_tips_per_session} style={inputStyle}
                   onChange={(e) => patch({ max_tips_per_session: Number(e.target.value) })}
                   className="w-full rounded-lg px-3 py-2 text-sm" />
          </Row>
        </div>

        <div className="space-y-3">
          {cfg.tips.map((tip, i) => (
            <div key={i} className="rounded-xl p-3" style={{ border: "1px solid var(--border)" }}>
              <div className="flex gap-2">
                <input value={tip.id} placeholder="ma-goi-y" style={inputStyle}
                       onChange={(e) => patchTip(i, { id: e.target.value })}
                       className="w-40 rounded-lg px-2 py-1.5 font-mono text-xs" />
                <input value={tip.route || ""} placeholder="/datasets" style={inputStyle}
                       onChange={(e) => patchTip(i, { route: e.target.value })}
                       className="w-40 rounded-lg px-2 py-1.5 font-mono text-xs" />
                <button onClick={() => patch({ tips: cfg.tips.filter((_, j) => j !== i) })}
                        className="ml-auto rounded-lg px-2 py-1.5 text-xs" style={{ color: "#dc2626" }}>Xoá</button>
              </div>
              <input value={tip.text} placeholder="Nội dung gợi ý" style={inputStyle}
                     onChange={(e) => patchTip(i, { text: e.target.value })}
                     className="mt-2 w-full rounded-lg px-2 py-1.5 text-sm" />
              <input value={tip.ask || ""} placeholder="Câu hỏi điền sẵn khi bấm Hỏi thêm" style={inputStyle}
                     onChange={(e) => patchTip(i, { ask: e.target.value })}
                     className="mt-2 w-full rounded-lg px-2 py-1.5 text-xs" />
            </div>
          ))}
          <button onClick={() => patch({ tips: [...cfg.tips, { id: `goi-y-${cfg.tips.length + 1}`, text: "" }] })}
                  className="rounded-lg px-3 py-1.5 text-xs font-medium"
                  style={{ border: "1px dashed var(--border)", color: "var(--muted)" }}>
            + Thêm gợi ý
          </button>
        </div>
      </Card>

      <div className="sticky bottom-4 flex items-center gap-3 rounded-2xl px-4 py-3"
           style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
        <button onClick={save} disabled={saving}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                style={{ background: "var(--accent)" }}>
          {saving ? "Đang lưu…" : "Lưu cấu hình"}
        </button>
        {saved && <span className="text-xs text-green-600">Đã lưu</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
        {cfg.updated_at && !saved && !error && (
          <span className="text-xs" style={{ color: "var(--muted)" }}>
            Cập nhật lần cuối {new Date(cfg.updated_at).toLocaleString("vi-VN")}
          </span>
        )}
      </div>
    </div>
  );
}
