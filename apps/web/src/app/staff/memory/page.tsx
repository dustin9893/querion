"use client";

/**
 * "Trợ lý nhớ gì về tôi" — trang cán bộ tự kiểm soát bộ nhớ của mình.
 *
 * Nguyên tắc: thấy được, sửa được, xoá được, tạm dừng được. Không tóm tắt, không giấu mục nào,
 * vì cá nhân hoá mà người dùng không nhìn thấy thì giống rò rỉ hơn là tính năng.
 *
 * Hai công tắc tách rời có chủ đích. Phần lớn người muốn "ngừng học thêm" chứ không muốn "xoá hết
 * những gì đã học"; gộp làm một là ép họ chọn cái họ không muốn.
 */
import { useCallback, useEffect, useState } from "react";

import {
  CATEGORY_ICON,
  clearMemory,
  deleteMemory,
  getMemory,
  setMemoryPaused,
  updateMemory,
  type MemoryItem,
  type MemoryPage,
} from "@/lib/api/memory";

function timeAgo(iso: string | null): string {
  if (!iso) return "chưa dùng lại";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "hôm nay";
  if (days === 1) return "hôm qua";
  if (days < 30) return `${days} ngày trước`;
  return `${Math.floor(days / 30)} tháng trước`;
}

export default function StaffMemoryPage() {
  const [page, setPage] = useState<MemoryPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [paused, setPaused] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);

  const reload = useCallback(async () => {
    try {
      const data = await getMemory();
      setPage(data);
      setPaused(data.paused);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không tải được bộ nhớ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const patch = async (item: MemoryItem, data: { text?: string; pinned?: boolean }) => {
    setError("");
    try {
      await updateMemory(item.id, data);
      await reload();
      setEditingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Không lưu được");
    }
  };

  const remove = async (item: MemoryItem) => {
    await deleteMemory(item.id).catch((e) => setError(String(e.message || e)));
    await reload();
  };

  if (loading) return <p className="text-sm opacity-70">Đang tải…</p>;
  if (!page) return <p className="text-sm text-red-600">{error || "Không tải được"}</p>;

  const grouped = Object.entries(page.categories).map(([key, label]) => ({
    key, label, items: page.items.filter((m) => m.category === key),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="mx-auto max-w-3xl space-y-5 pb-20">
      <header>
        <h1 className="text-lg font-semibold">Trợ lý nhớ gì về tôi</h1>
        <p className="mt-1 text-xs opacity-70">
          Trợ lý ghi lại cách anh/chị làm việc để trả lời hợp hơn. Mọi dòng dưới đây đều sửa và xoá
          được. Bộ nhớ tự hết hạn sau {page.retention_days} ngày nếu không dùng lại.
        </p>
      </header>

      {!page.enabled && (
        <div className="rounded-xl px-4 py-3 text-xs"
             style={{ background: "rgba(217,119,6,0.10)", border: "1px solid rgba(217,119,6,0.35)" }}>
          Đơn vị đang tắt bộ nhớ cá nhân, nên trợ lý không ghi nhớ gì mới.
        </div>
      )}

      <section className="rounded-2xl p-4" style={{ border: "1px solid var(--border)" }}>
        <h2 className="text-sm font-semibold">Hồ sơ nghề nghiệp</h2>
        <p className="mt-0.5 text-[11px] opacity-60">Phần này do đơn vị quản lý, anh/chị không sửa ở đây.</p>
        <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs opacity-80">
          <span>{page.profile.name}</span>
          {page.profile.employee_code && <span>Mã {page.profile.employee_code}</span>}
          {page.profile.position && <span>Chức danh {page.profile.position}</span>}
          {page.profile.branch && <span>{page.profile.branch}</span>}
          {page.profile.department && <span>{page.profile.department}</span>}
        </div>
      </section>

      {page.items.length === 0 ? (
        <section className="rounded-2xl p-5 text-sm opacity-70" style={{ border: "1px solid var(--border)" }}>
          Trợ lý chưa ghi nhớ gì về anh/chị. Cứ hỏi và làm việc bình thường; khi thấy điều đáng nhớ
          về cách anh/chị muốn được trả lời, nó sẽ báo ngay dưới câu trả lời.
        </section>
      ) : (
        grouped.map((g) => (
          <section key={g.key} className="space-y-2">
            <h2 className="text-sm font-semibold">
              <span aria-hidden className="mr-1.5">{CATEGORY_ICON[g.key]}</span>{g.label}
            </h2>
            {g.items.map((m) => (
              <div key={m.id} className="rounded-xl p-3" style={{ border: "1px solid var(--border)" }}>
                {editingId === m.id ? (
                  <div className="space-y-2">
                    <textarea value={draft} rows={2} autoFocus
                              onChange={(e) => setDraft(e.target.value)}
                              className="w-full rounded-lg px-3 py-2 text-sm"
                              style={{ background: "var(--background)", border: "1px solid var(--border)" }} />
                    <div className="flex gap-2">
                      <button onClick={() => patch(m, { text: draft })}
                              className="rounded-lg px-3 py-1 text-[11px] font-semibold text-white"
                              style={{ background: "var(--accent)" }}>Lưu</button>
                      <button onClick={() => setEditingId(null)} className="text-[11px] opacity-70">Huỷ</button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="text-sm">{m.text}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[11px] opacity-60">
                      <span>Dùng lần cuối {timeAgo(m.last_used_at)}</span>
                      {m.pinned && <span style={{ color: "var(--accent)" }}>Đã ghim, không hết hạn</span>}
                      <button onClick={() => { setEditingId(m.id); setDraft(m.text); }}
                              className="ml-auto hover:opacity-100">Sửa</button>
                      <button onClick={() => patch(m, { pinned: !m.pinned })} className="hover:opacity-100">
                        {m.pinned ? "Bỏ ghim" : "Ghim"}
                      </button>
                      <button onClick={() => remove(m)} className="hover:opacity-100" style={{ color: "#dc2626" }}>Xoá</button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </section>
        ))
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}

      <section className="rounded-2xl p-4" style={{ border: "1px solid var(--border)" }}>
        <h2 className="text-sm font-semibold">Trợ lý không bao giờ nhớ</h2>
        <ul className="mt-2 space-y-1 text-xs opacity-75">
          {page.never_remembers.map((line) => (
            <li key={line} className="flex gap-2"><span aria-hidden>·</span>{line}</li>
          ))}
        </ul>
      </section>

      <section className="flex flex-wrap items-center gap-4 rounded-2xl p-4"
               style={{ border: "1px solid var(--border)" }}>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={paused} disabled={pausing}
                 onChange={async (e) => {
                   const next = e.target.checked;
                   setPaused(next);
                   setPausing(true);
                   try {
                     await setMemoryPaused(next);
                   } catch (err) {
                     setPaused(!next);  // máy chủ từ chối thì trả lại đúng trạng thái thật
                     setError(err instanceof Error ? err.message : "Không đổi được");
                   } finally {
                     setPausing(false);
                   }
                 }} />
          Tạm dừng ghi nhớ
        </label>
        <span className="text-[11px] opacity-60">
          Giữ nguyên những gì đã nhớ, chỉ ngừng học thêm. Lựa chọn này lưu theo tài khoản nên có
          hiệu lực trên mọi thiết bị.
        </span>
        {confirmClear ? (
          <span className="ml-auto flex items-center gap-2 text-xs">
            Xoá toàn bộ {page.items.length} bản ghi?
            <button onClick={async () => { await clearMemory(); setConfirmClear(false); await reload(); }}
                    className="rounded-lg px-3 py-1 text-[11px] font-semibold text-white"
                    style={{ background: "#dc2626" }}>Xoá hết</button>
            <button onClick={() => setConfirmClear(false)} className="text-[11px] opacity-70">Huỷ</button>
          </span>
        ) : (
          <button onClick={() => setConfirmClear(true)} className="ml-auto text-xs" style={{ color: "#dc2626" }}>
            Xoá tất cả
          </button>
        )}
      </section>
    </div>
  );
}
