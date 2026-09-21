"use client";

/**
 * Kỹ năng của trợ lý.
 *
 * Trình soạn ở đây đầu tư nặng nhất vào ô "Dùng khi nào", vì đó là thứ duy nhất mô hình đọc để
 * quyết định kích hoạt. Mô tả mơ hồ làm hỏng cả kỹ năng dù thân bài viết hay tới đâu, nên giao
 * diện chấm điểm ngay lúc gõ, cảnh báo khi trùng ý với kỹ năng khác, và cho thử một câu hỏi thật
 * trước khi gắn vào trợ lý.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { listDatasets, type DatasetResponse } from "@/lib/api/datasets";
import {
  QUALITY_COLOR,
  QUALITY_LABEL,
  STATUS_LABEL,
  createSkill,
  deleteSkill,
  exportAllSkills,
  exportSkill,
  importSkills,
  listSkills,
  skillTemplate,
  trySkills,
  updateSkill,
  type Skill,
  type SkillDraft,
  type SkillTryResult,
} from "@/lib/api/skills";

const input = {
  background: "var(--background)",
  border: "1px solid var(--border)",
  color: "var(--foreground)",
};

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl p-5" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
      {children}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium" style={{ color: "var(--foreground)" }}>{label}</span>
      {hint && <span className="ml-2 text-[11px]" style={{ color: "var(--muted)" }}>{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

export default function SkillsPage() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [datasets, setDatasets] = useState<DatasetResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Skill | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([
        listSkills(),
        listDatasets().catch(() => []),
      ]);
      setSkills(s);
      setDatasets(d as DatasetResponse[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được danh sách kỹ năng");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const onImport = async (file: File) => {
    setError(""); setNotice("");
    try {
      const r = await importSkills(file);
      setNotice(r.detail);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không nhập được tệp");
    }
  };

  if (loading) return <p className="text-sm" style={{ color: "var(--muted)" }}>Đang tải…</p>;

  return (
    <div className="space-y-5 pb-20">
      <header className="flex items-start gap-4">
        <div className="flex-1">
          <h1 className="text-lg font-semibold" style={{ color: "var(--foreground)" }}>Kỹ năng</h1>
          <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
            Bí kíp nghiệp vụ trợ lý nạp khi cần. Trợ lý luôn thấy tên và mô tả của mọi kỹ năng, nhưng
            chỉ đọc toàn văn kỹ năng khớp câu hỏi, nên thêm kỹ năng không làm nặng mọi câu trả lời.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <input ref={fileRef} type="file" accept=".md,.zip" className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) onImport(f); e.target.value = ""; }} />
          <button onClick={() => fileRef.current?.click()}
                  className="rounded-lg px-3 py-2 text-xs font-medium"
                  style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>Nhập SKILL.md</button>
          <button onClick={() => exportAllSkills().catch((e) => setError(String(e.message || e)))}
                  className="rounded-lg px-3 py-2 text-xs font-medium"
                  style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>Xuất tất cả</button>
          <button onClick={() => { setCreating(true); setEditing(null); }}
                  className="rounded-lg px-4 py-2 text-xs font-semibold text-white"
                  style={{ background: "var(--accent)" }}>+ Kỹ năng mới</button>
        </div>
      </header>

      {error && <p className="text-xs text-red-600">{error}</p>}
      {notice && <p className="text-xs text-green-600">{notice}</p>}

      {skills.length === 0 ? (
        <Card>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Chưa có kỹ năng nào. Kỹ năng hợp lý nhất để bắt đầu là việc mà cán bộ hỏi đi hỏi lại và
            lần nào cũng cần làm theo đúng một trình tự.
          </p>
        </Card>
      ) : (
        <div className="space-y-2">
          {skills.map((s) => (
            <SkillRow key={s.id} skill={s} onEdit={() => { setEditing(s); setCreating(false); }}
                      onExport={() => exportSkill(s.id, s.slug).catch((e) => setError(String(e.message || e)))} />
          ))}
        </div>
      )}

      {(creating || editing) && (
        <SkillEditor
          skill={editing}
          datasets={datasets}
          onClose={() => { setCreating(false); setEditing(null); }}
          onSaved={async () => { setCreating(false); setEditing(null); await reload(); }}
          onDeleted={async () => { setCreating(false); setEditing(null); await reload(); }}
        />
      )}
    </div>
  );
}

function SkillRow({ skill, onEdit, onExport }: { skill: Skill; onEdit: () => void; onExport: () => void }) {
  const q = skill.quality;
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>{skill.name}</span>
            <code className="rounded px-1.5 py-0.5 text-[10px]"
                  style={{ background: "var(--background)", color: "var(--muted)" }}>{skill.slug}</code>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                  style={{
                    background: skill.status === "published" ? "rgba(22,163,74,0.12)" : "rgba(100,116,139,0.12)",
                    color: skill.status === "published" ? "#16a34a" : "#64748b",
                  }}>{STATUS_LABEL[skill.status]}</span>
            {skill.share_scope === "bank" && (
              <span className="rounded-full px-2 py-0.5 text-[10px]"
                    style={{ background: "rgba(59,130,246,0.12)", color: "#2563eb" }}>Toàn ngân hàng</span>
            )}
            {skill.allow_customer && (
              <span className="rounded-full px-2 py-0.5 text-[10px]"
                    style={{ background: "rgba(217,119,6,0.12)", color: "#d97706" }}>Mở cho khách hàng</span>
            )}
            {!skill.own_unit && (
              <span className="text-[10px]" style={{ color: "var(--muted)" }}>của đơn vị khác</span>
            )}
          </div>
          <p className="mt-1.5 text-xs leading-snug" style={{ color: "var(--muted)" }}>{skill.description}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px]" style={{ color: "var(--muted)" }}>
            <span>{skill.version}{skill.effective_from ? ` · hiệu lực ${skill.effective_from}` : ""}</span>
            {skill.reference_document_ids.length > 0 && (
              <span>dựa trên {skill.reference_document_ids.length} văn bản</span>
            )}
            <span>{skill.app_count} trợ lý dùng</span>
            {q && <span style={{ color: QUALITY_COLOR[q.level] }}>Mô tả: {QUALITY_LABEL[q.level]}</span>}
            {skill.overlaps.length > 0 && (
              <span style={{ color: "#d97706" }}>⚠ Dễ nhầm với {skill.overlaps.map((o) => o.name).join(", ")}</span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={onExport} className="rounded-lg px-2.5 py-1.5 text-[11px]"
                  style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>Xuất</button>
          {skill.own_unit && (
            <button onClick={onEdit} className="rounded-lg px-3 py-1.5 text-[11px] font-medium"
                    style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>Sửa</button>
          )}
        </div>
      </div>
    </div>
  );
}

function SkillEditor({
  skill, datasets, onClose, onSaved, onDeleted,
}: {
  skill: Skill | null;
  datasets: DatasetResponse[];
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const [draft, setDraft] = useState<SkillDraft>(() => skill ? {
    name: skill.name, description: skill.description, body: skill.body, version: skill.version,
    effective_from: skill.effective_from, status: skill.status, share_scope: skill.share_scope,
    allow_customer: skill.allow_customer,
    preferred_dataset_ids: skill.preferred_dataset_ids,
  } : { name: "", description: "", body: "", version: "v1.0", status: "draft" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [tryQuery, setTryQuery] = useState("");
  const [tryResult, setTryResult] = useState<SkillTryResult | null>(null);
  const [trying, setTrying] = useState(false);

  useEffect(() => {
    if (!skill && !draft.body) {
      skillTemplate().then((t) => setDraft((d) => ({ ...d, body: t.body }))).catch(() => {});
    }
    // chỉ nạp khung một lần khi mở trình soạn cho kỹ năng mới
  }, [skill, draft.body]);

  const desc = (draft.description || "").trim();
  const localQuality = desc.length === 0 ? null
    : desc.length < 40 ? { level: "yeu", note: "Mô tả quá ngắn để phân biệt với kỹ năng khác" }
    : !/khi |dùng khi|lúc |trường hợp|nếu /i.test(desc)
      ? { level: "tam", note: 'Nên thêm vế "Dùng khi…" để mô hình biết lúc nào kích hoạt' }
      : { level: "tot", note: "Đủ để mô hình phân biệt" };

  const bodyLines = (draft.body || "").split("\n").length;

  const save = async () => {
    setSaving(true); setError("");
    try {
      if (skill) await updateSkill(skill.id, draft);
      else await createSkill(draft);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không lưu được");
    } finally {
      setSaving(false);
    }
  };

  const runTry = async () => {
    if (!tryQuery.trim()) return;
    setTrying(true);
    try {
      setTryResult(await trySkills(tryQuery.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không thử được");
    } finally {
      setTrying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-6"
         style={{ background: "rgba(15,23,42,0.45)" }} onClick={onClose}>
      <div className="w-full max-w-3xl space-y-4 rounded-2xl p-6" onClick={(e) => e.stopPropagation()}
           style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
        <div className="flex items-center gap-3">
          <h2 className="flex-1 text-base font-semibold" style={{ color: "var(--foreground)" }}>
            {skill ? `Sửa kỹ năng: ${skill.name}` : "Kỹ năng mới"}
          </h2>
          <button onClick={onClose} className="text-xs" style={{ color: "var(--muted)" }}>Đóng</button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Tên kỹ năng">
            <input value={draft.name || ""} style={input}
                   onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                   className="w-full rounded-lg px-3 py-2 text-sm" placeholder="Kiểm tra điều kiện giải ngân" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Phiên bản">
              <input value={draft.version || ""} style={input}
                     onChange={(e) => setDraft({ ...draft, version: e.target.value })}
                     className="w-full rounded-lg px-3 py-2 text-sm" placeholder="v1.0" />
            </Field>
            <Field label="Hiệu lực từ">
              <input value={draft.effective_from || ""} style={input}
                     onChange={(e) => setDraft({ ...draft, effective_from: e.target.value })}
                     className="w-full rounded-lg px-3 py-2 text-sm" placeholder="01/10/2026" />
            </Field>
          </div>
        </div>

        <Field label="Dùng khi nào"
               hint="thứ duy nhất mô hình đọc để quyết định kích hoạt — viết kỹ chỗ này nhất">
          <textarea value={draft.description || ""} rows={3} style={input}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                    className="w-full rounded-lg px-3 py-2 text-sm"
                    placeholder="Rà soát một hồ sơ tín dụng đã đủ điều kiện giải ngân chưa và còn thiếu gì. Dùng khi cán bộ hỏi về giải ngân, chứng từ còn thiếu, hoặc nhắc tới một mã hồ sơ." />
        </Field>
        {localQuality && (
          <p className="-mt-2 text-[11px]" style={{ color: QUALITY_COLOR[localQuality.level] }}>
            {QUALITY_LABEL[localQuality.level]} · {localQuality.note} · {desc.length} ký tự
          </p>
        )}
        {skill && skill.overlaps.length > 0 && (
          <div className="rounded-xl p-3 text-[11px]"
               style={{ background: "rgba(217,119,6,0.08)", border: "1px solid rgba(217,119,6,0.35)", color: "#b45309" }}>
            Mô tả này gần giống {skill.overlaps.map((o) => `${o.name} (${o.score})`).join(", ")}.
            Hai kỹ năng nói cùng một chuyện thì mô hình sẽ chọn nhầm, và người dùng không hiểu vì sao.
          </div>
        )}

        <Field label="Nội dung kỹ năng" hint={`${bodyLines} dòng, nên dưới 500`}>
          <textarea value={draft.body || ""} rows={14} style={input}
                    onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                    className="w-full rounded-lg px-3 py-2 font-mono text-xs" />
        </Field>
        <p className="-mt-2 text-[11px]" style={{ color: "var(--muted)" }}>
          Đừng chép số liệu quy định vào đây. Con số nằm trong văn bản để trích dẫn được; viết vào kỹ
          năng thì đổi quy định là kỹ năng sai âm thầm. Hãy viết &ldquo;tra tỉ lệ trong Quy định TSBĐ&rdquo;
          thay vì viết thẳng con số.
        </p>

        <div className="grid grid-cols-1 gap-4">
          <Field label="Kho tri thức ưu tiên" hint="kỹ năng này chạy thì tra đúng kho đây">
            <div className="max-h-28 space-y-1 overflow-y-auto rounded-lg p-2" style={{ border: "1px solid var(--border)" }}>
              {datasets.map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-xs" style={{ color: "var(--foreground)" }}>
                  <input type="checkbox" checked={(draft.preferred_dataset_ids || []).includes(d.id)}
                         onChange={(e) => setDraft({
                           ...draft,
                           preferred_dataset_ids: e.target.checked
                             ? [...(draft.preferred_dataset_ids || []), d.id]
                             : (draft.preferred_dataset_ids || []).filter((x) => x !== d.id),
                         })} />
                  {d.name}
                </label>
              ))}
              {datasets.length === 0 && <span className="text-[11px]" style={{ color: "var(--muted)" }}>Chưa có kho</span>}
            </div>
          </Field>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--foreground)" }}>
            <input type="checkbox" checked={draft.status === "published"}
                   onChange={(e) => setDraft({ ...draft, status: e.target.checked ? "published" : "draft" })} />
            Công bố (trợ lý chỉ dùng kỹ năng đã công bố)
          </label>
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--foreground)" }}>
            <input type="checkbox" checked={draft.share_scope === "bank"}
                   onChange={(e) => setDraft({ ...draft, share_scope: e.target.checked ? "bank" : "unit" })} />
            Chia sẻ toàn ngân hàng
          </label>
          <label className="flex items-center gap-2 text-xs" style={{ color: "var(--foreground)" }}>
            <input type="checkbox" checked={!!draft.allow_customer}
                   onChange={(e) => setDraft({ ...draft, allow_customer: e.target.checked })} />
            Cho phép dùng ở kênh khách hàng
          </label>
        </div>

        <div className="rounded-xl p-3" style={{ border: "1px dashed var(--border)" }}>
          <Field label="Thử kỹ năng" hint="gõ một câu hỏi thật, xem kỹ năng nào sẽ được kích hoạt">
            <div className="flex gap-2">
              <input value={tryQuery} style={input}
                     onChange={(e) => setTryQuery(e.target.value)}
                     onKeyDown={(e) => { if (e.key === "Enter") runTry(); }}
                     className="flex-1 rounded-lg px-3 py-2 text-sm"
                     placeholder="Hồ sơ HS2026-0412 đã giải ngân được chưa?" />
              <button onClick={runTry} disabled={trying}
                      className="rounded-lg px-3 py-2 text-xs font-medium text-white disabled:opacity-60"
                      style={{ background: "var(--accent)" }}>{trying ? "Đang thử…" : "Thử"}</button>
            </div>
          </Field>
          {tryResult && (
            <div className="mt-2 text-[11px]" style={{ color: "var(--muted)" }}>
              {tryResult.chosen
                ? <span>Sẽ kích hoạt <b style={{ color: "var(--foreground)" }}>{tryResult.chosen.name}</b> (điểm {tryResult.best_score}, ngưỡng {tryResult.threshold})</span>
                : <span>Không kích hoạt kỹ năng nào. Điểm cao nhất {tryResult.best_score}, dưới ngưỡng {tryResult.threshold}.</span>}
              <div className="mt-1 space-y-0.5">
                {tryResult.scores.slice(0, 4).map((s) => (
                  <div key={s.id}>{s.score.toFixed(3)} — {s.name}</div>
                ))}
              </div>
            </div>
          )}
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <div className="flex items-center gap-3">
          <button onClick={save} disabled={saving || !draft.name || !draft.description}
                  className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
                  style={{ background: "var(--accent)" }}>
            {saving ? "Đang lưu…" : "Lưu kỹ năng"}
          </button>
          {skill && (
            <button onClick={async () => { await deleteSkill(skill.id); onDeleted(); }}
                    className="ml-auto text-xs" style={{ color: "#dc2626" }}>Xoá kỹ năng</button>
          )}
        </div>
      </div>
    </div>
  );
}
