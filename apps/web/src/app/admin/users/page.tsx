"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { api } from "@/lib/api";

/**
 * Người dùng quản trị (super admin only): create admin users and assign them to units
 * (workspaces) with a role. Membership calls go to /v1/workspaces/{id}/members with an
 * explicit X-Workspace-Id for the target unit — the auto-injected header would be the
 * super admin's currently selected unit, not necessarily the one being edited.
 */

type WsRole = "owner" | "editor" | "viewer";

interface Membership { workspace_id: string; ws_role: WsRole | string; workspace_name?: string | null }
interface UserItem { id: string; email: string; name: string; role: string; is_active: boolean; workspaces: Membership[] }
interface WorkspaceItem { id: string; name: string }

const ROLE_LABEL: Record<string, string> = { owner: "Chủ đơn vị", editor: "Biên tập", viewer: "Chỉ xem" };
const ROLE_HINT = "Chủ đơn vị: quản lý thành viên, mở trợ lý cho toàn ngân hàng · Biên tập: tạo/sửa kho tri thức, trợ lý, luồng · Chỉ xem: chỉ đọc";
const inputStyle = { background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" };

export default function AdminUsersPage() {
  const { isSuper } = useAuth();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // create form
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", name: "", workspace_id: "", ws_role: "owner" as WsRole });
  const [creating, setCreating] = useState(false);

  // per-user "assign to unit" row
  const [assignFor, setAssignFor] = useState<string | null>(null);
  const [assign, setAssign] = useState<{ workspace_id: string; ws_role: WsRole }>({ workspace_id: "", ws_role: "owner" });
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [u, w] = await Promise.all([api.get<UserItem[]>("/v1/users"), api.get<WorkspaceItem[]>("/v1/workspaces")]);
      setUsers(u); setWorkspaces(w);
    } catch (e: any) { setError(e.message || "Không tải được dữ liệu"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const wsHeaders = (wsId: string) => ({ headers: { "X-Workspace-Id": wsId } });

  const addMembership = async (userId: string, wsId: string, role: WsRole) => {
    await api.post(`/v1/workspaces/${wsId}/members`, { user_id: userId, ws_role: role }, wsHeaders(wsId));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setCreating(true);
    try {
      const created = await api.post<UserItem>("/v1/users", { email: form.email, password: form.password, name: form.name });
      if (form.workspace_id) await addMembership(created.id, form.workspace_id, form.ws_role);
      setShowCreate(false);
      setForm({ email: "", password: "", name: "", workspace_id: "", ws_role: "owner" });
      await load();
    } catch (err: any) { setError(err.message || "Tạo người dùng thất bại"); }
    finally { setCreating(false); }
  };

  const toggleActive = async (u: UserItem) => {
    setBusy(u.id);
    try { await api.patch(`/v1/users/${u.id}`, { is_active: !u.is_active }); await load(); }
    catch (err: any) { setError(err.message); }
    finally { setBusy(null); }
  };

  const handleAssign = async (u: UserItem) => {
    if (!assign.workspace_id) return;
    setBusy(u.id); setError("");
    try {
      await addMembership(u.id, assign.workspace_id, assign.ws_role);
      setAssignFor(null); setAssign({ workspace_id: "", ws_role: "owner" });
      await load();
    } catch (err: any) { setError(err.message || "Gán đơn vị thất bại"); }
    finally { setBusy(null); }
  };

  const changeRole = async (u: UserItem, m: Membership, role: WsRole) => {
    setBusy(u.id); setError("");
    try { await api.patch(`/v1/workspaces/${m.workspace_id}/members/${u.id}`, { ws_role: role }, wsHeaders(m.workspace_id)); await load(); }
    catch (err: any) { setError(err.message || "Đổi vai trò thất bại"); }
    finally { setBusy(null); }
  };

  const removeMembership = async (u: UserItem, m: Membership) => {
    if (!confirm(`Gỡ ${u.email} khỏi đơn vị "${m.workspace_name || m.workspace_id}"?`)) return;
    setBusy(u.id); setError("");
    try { await api.delete(`/v1/workspaces/${m.workspace_id}/members/${u.id}`, wsHeaders(m.workspace_id)); await load(); }
    catch (err: any) { setError(err.message || "Gỡ khỏi đơn vị thất bại"); }
    finally { setBusy(null); }
  };

  if (!isSuper) {
    return (
      <div className="flex items-center justify-center h-64">
        <p style={{ color: "var(--muted)" }}>Chỉ super admin mới truy cập được trang này.</p>
      </div>
    );
  }

  const wsName = (id: string) => workspaces.find((w) => w.id === id)?.name || id;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Người dùng quản trị</h2>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
            Tạo tài khoản quản trị và gán vào đơn vị (workspace) với vai trò. Một người có thể quản trị nhiều đơn vị.
          </p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)} className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white" style={{ background: "var(--accent)" }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          Tạo người dùng
        </button>
      </div>

      <p className="text-[11px] mb-4" style={{ color: "var(--muted)" }}>{ROLE_HINT}. Super admin có toàn quyền trên mọi đơn vị, không cần gán.</p>

      {error && <p className="mb-3 text-sm rounded-lg px-3 py-2" style={{ color: "#ef4444", background: "rgba(239,68,68,0.08)" }}>{error}</p>}

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="rounded-xl p-4 mb-6 grid gap-3" style={{ background: "var(--card)", border: "1px solid var(--border)", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <input type="email" placeholder="Email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="rounded-lg px-3 py-2 text-sm outline-none" style={inputStyle} />
          <input type="text" placeholder="Họ tên" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="rounded-lg px-3 py-2 text-sm outline-none" style={inputStyle} />
          <input type="password" placeholder="Mật khẩu" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="rounded-lg px-3 py-2 text-sm outline-none" style={inputStyle} />
          <select value={form.workspace_id} onChange={(e) => setForm({ ...form, workspace_id: e.target.value })} className="rounded-lg px-3 py-2 text-sm outline-none" style={inputStyle} data-testid="create-unit">
            <option value="">— Gán vào đơn vị (tuỳ chọn) —</option>
            {workspaces.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <select value={form.ws_role} onChange={(e) => setForm({ ...form, ws_role: e.target.value as WsRole })} disabled={!form.workspace_id} className="rounded-lg px-3 py-2 text-sm outline-none" style={inputStyle} data-testid="create-role">
            {(["owner", "editor", "viewer"] as WsRole[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
          <div className="flex items-center gap-2">
            <button type="submit" disabled={creating} className="rounded-lg px-4 py-2 text-sm font-medium text-white" style={{ background: "var(--accent)" }}>{creating ? "..." : "Tạo"}</button>
            <button type="button" onClick={() => setShowCreate(false)} className="rounded-lg px-4 py-2 text-sm" style={{ color: "var(--muted)" }}>Huỷ</button>
          </div>
        </form>
      )}

      {/* Table */}
      <div className="rounded-xl overflow-hidden responsive-table-wrap" style={{ border: "1px solid var(--border)" }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: "var(--card)" }}>
              {["Email", "Họ tên", "Vai trò hệ thống", "Đơn vị (workspace) · vai trò", "Trạng thái", ""].map((h, i) => (
                <th key={h || i} className={`${i === 5 ? "text-right" : "text-left"} px-4 py-3 font-medium`} style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSuperRow = u.role === "super_admin";
              const assignable = workspaces.filter((w) => !u.workspaces.some((m) => m.workspace_id === w.id));
              return (
                <tr key={u.id} style={{ borderBottom: "1px solid var(--border)", opacity: busy === u.id ? 0.6 : 1 }} data-testid={`user-${u.email}`}>
                  <td className="px-4 py-3" style={{ color: "var(--foreground)" }}>{u.email}</td>
                  <td className="px-4 py-3" style={{ color: "var(--foreground)" }}>{u.name}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-2 py-0.5 rounded font-medium whitespace-nowrap"
                      style={{ background: isSuperRow ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)", color: isSuperRow ? "#ef4444" : "#3b82f6" }}>
                      {isSuperRow ? "Super admin" : "Admin"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {isSuperRow ? (
                      <span className="text-xs" style={{ color: "var(--muted)" }}>Toàn hệ thống</span>
                    ) : (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {u.workspaces.length === 0 && assignFor !== u.id && (
                          <span className="text-xs" style={{ color: "#f59e0b" }}>Chưa gán đơn vị</span>
                        )}
                        {u.workspaces.map((m) => (
                          <span key={m.workspace_id} className="inline-flex items-center gap-1 rounded-full pl-2.5 pr-1 py-0.5 text-xs"
                            style={{ background: "var(--accent-glow)", border: "1px solid var(--border)", color: "var(--foreground)" }} data-testid={`membership-${u.email}-${m.workspace_id}`}>
                            <span className="font-medium truncate max-w-[200px]">{m.workspace_name || wsName(m.workspace_id)}</span>
                            <select value={m.ws_role} onChange={(e) => changeRole(u, m, e.target.value as WsRole)} disabled={busy === u.id}
                              className="text-[11px] rounded-md px-1 py-0.5 outline-none" style={{ background: "transparent", color: "var(--accent-text)", border: "none" }} aria-label={`Vai trò tại ${m.workspace_name || ""}`}>
                              {(["owner", "editor", "viewer"] as WsRole[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                            </select>
                            <button type="button" onClick={() => removeMembership(u, m)} disabled={busy === u.id} className="rounded-full px-1 leading-none" style={{ color: "var(--muted)" }} title="Gỡ khỏi đơn vị" aria-label={`Gỡ khỏi ${m.workspace_name || ""}`}>×</button>
                          </span>
                        ))}
                        {assignFor === u.id ? (
                          <span className="inline-flex items-center gap-1.5">
                            <select value={assign.workspace_id} onChange={(e) => setAssign({ ...assign, workspace_id: e.target.value })} className="text-xs rounded-lg px-2 py-1 outline-none max-w-[220px]" style={inputStyle} autoFocus data-testid="assign-unit">
                              <option value="">— Chọn đơn vị —</option>
                              {assignable.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
                            </select>
                            <select value={assign.ws_role} onChange={(e) => setAssign({ ...assign, ws_role: e.target.value as WsRole })} className="text-xs rounded-lg px-2 py-1 outline-none" style={inputStyle} data-testid="assign-role">
                              {(["owner", "editor", "viewer"] as WsRole[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                            </select>
                            <button type="button" onClick={() => handleAssign(u)} disabled={!assign.workspace_id || busy === u.id} className="text-xs rounded-lg px-2.5 py-1 font-medium text-white" style={{ background: "var(--accent)" }} data-testid="assign-save">Gán</button>
                            <button type="button" onClick={() => setAssignFor(null)} className="text-xs px-1" style={{ color: "var(--muted)" }}>Huỷ</button>
                          </span>
                        ) : (
                          assignable.length > 0 && u.is_active && (
                            <button type="button" onClick={() => { setAssignFor(u.id); setAssign({ workspace_id: "", ws_role: "owner" }); }}
                              className="text-xs rounded-full px-2.5 py-0.5" style={{ border: "1px dashed var(--border)", color: "var(--accent)" }} data-testid={`assign-${u.email}`}>
                              + Gán đơn vị
                            </button>
                          )
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-xs px-2 py-0.5 rounded font-medium whitespace-nowrap"
                      style={{ background: u.is_active ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)", color: u.is_active ? "#22c55e" : "#ef4444" }}>
                      {u.is_active ? "Hoạt động" : "Vô hiệu"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {!isSuperRow && (
                      <button onClick={() => toggleActive(u)} disabled={busy === u.id} className="text-xs px-2 py-1 rounded whitespace-nowrap" style={{ color: "var(--muted)", border: "1px solid var(--border)" }}>
                        {u.is_active ? "Vô hiệu hoá" : "Kích hoạt"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {loading && <p className="p-4 text-sm" style={{ color: "var(--muted)" }}>Đang tải...</p>}
        {!loading && users.length === 0 && <p className="p-4 text-sm" style={{ color: "var(--muted)" }}>Chưa có người dùng</p>}
      </div>
    </div>
  );
}
