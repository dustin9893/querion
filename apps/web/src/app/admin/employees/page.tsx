"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth, useWorkspace, usePermission } from "@/components/providers/AuthProvider";
import { api } from "@/lib/api";

interface EmployeeItem {
  id: string;
  email: string;
  name: string;
  employee_code: string | null;
  branch: string | null;
  department: string | null;
  position: string | null;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  workspace_id: string | null;
  workspace_name: string | null;
}

interface UnitOption { id: string; name: string }

const POSITIONS = ["RM", "CA", "GDV", "OPS", "CCO", "KSV", "Other"];
const DEFAULT_PASSWORD = "msb@123";

const inputStyle = { background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" };

export default function AdminEmployeesPage() {
  const { user, isSuper } = useAuth();
  const { isOwner } = usePermission(); // super admin or owner of the active unit
  const { activeWorkspace, workspaces: myWorkspaces } = useWorkspace();
  const [units, setUnits] = useState<UnitOption[]>([]);
  const [filterWs, setFilterWs] = useState<string>(""); // super admin: "" = all units
  const [employees, setEmployees] = useState<EmployeeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", employee_code: "", branch: "", department: "", position: "RM", workspace_id: "" });
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<{ created: number; skipped: number; errors: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const isAdmin = user?.role === "admin" || user?.role === "super_admin";
  // Unit admins always work inside the active unit; super admin may filter or see everyone
  const scopeWs = isSuper ? filterWs : (activeWorkspace?.workspace_id || "");

  const fetchEmployees = useCallback(async () => {
    if (!isSuper && !scopeWs) { setEmployees([]); setLoading(false); return; }
    setLoading(true);
    try { setEmployees(await api.get<EmployeeItem[]>(`/v1/employees${scopeWs ? `?workspace_id=${scopeWs}` : ""}`)); }
    catch { /* silent */ }
    finally { setLoading(false); }
  }, [isSuper, scopeWs]);

  useEffect(() => { fetchEmployees(); }, [fetchEmployees]);

  // Units to assign staff to: every workspace for super admin, otherwise the admin's memberships
  useEffect(() => {
    (async () => {
      try {
        const all = await api.get<{ id: string; name: string }[]>("/v1/workspaces");
        setUnits(all.map((w) => ({ id: w.id, name: w.name })));
      } catch {
        setUnits(myWorkspaces.map((w) => ({ id: w.workspace_id, name: w.workspace_name })));
      }
    })();
  }, [myWorkspaces]);

  const openAdd = () => {
    setForm((f) => ({ ...f, workspace_id: (isSuper ? (f.workspace_id || filterWs) : "") || activeWorkspace?.workspace_id || "" }));
    setShowAdd(true);
  };

  const handleUnitChange = async (emp: EmployeeItem, workspaceId: string) => {
    try {
      const updated = await api.patch<EmployeeItem>(`/v1/employees/${emp.id}`, { workspace_id: workspaceId });
      setEmployees((prev) => prev.map((e) => (e.id === emp.id ? updated : e)));
    } catch (err: any) { alert(err.message || "Không đổi được đơn vị"); }
  };

  const setField = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleAdd = async () => {
    if (!form.email.trim() || !form.name.trim()) return;
    setCreating(true);
    try {
      const e = await api.post<EmployeeItem>("/v1/employees", {
        email: form.email, name: form.name,
        employee_code: form.employee_code || null,
        branch: form.branch || null,
        department: form.department || null,
        position: form.position || null,
        workspace_id: form.workspace_id || null,
      });
      setEmployees((prev) => [e, ...prev]);
      setShowAdd(false);
      setForm({ email: "", name: "", employee_code: "", branch: "", department: "", position: "RM", workspace_id: activeWorkspace?.workspace_id || "" });
    } catch { /* silent */ }
    finally { setCreating(false); }
  };

  const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await api.upload<{ created: number; skipped: number; errors: string[] }>("/v1/employees/import-csv", formData);
      setImportResult(result);
      fetchEmployees();
    } catch { /* silent */ }
    finally { setImporting(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const handleDeactivate = async (id: string) => {
    try {
      await api.delete(`/v1/employees/${id}`);
      setEmployees((prev) => prev.map((s) => s.id === id ? { ...s, is_active: false } : s));
    } catch { /* silent */ }
  };

  if (!isAdmin) return <div className="text-center py-20 text-sm" style={{ color: "var(--muted)" }}>Không có quyền truy cập</div>;

  if (!isOwner) {
    return (
      <div className="flex items-center justify-center h-64 text-center px-6">
        <p className="text-sm" style={{ color: "var(--muted)" }}>Chỉ chủ đơn vị (owner) của đơn vị đang chọn hoặc super admin mới quản lý cán bộ.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6 page-header">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>Cán bộ</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>Quản lý tài khoản cán bộ dùng cổng Trợ lý (mật khẩu mặc định: {DEFAULT_PASSWORD})</p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleImportCSV} />
          <button onClick={() => fileRef.current?.click()} disabled={importing}
            className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium"
            style={{ background: "var(--card)", color: "var(--foreground)", border: "1px solid var(--border)" }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1V10M3 6L7 10L11 6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
            {importing ? "Đang nhập..." : "Nhập CSV"}
          </button>
          <button onClick={openAdd}
            className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium"
            style={{ background: "var(--accent)", color: "#fff" }}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 2V12M2 7H12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            Thêm cán bộ
          </button>
        </div>
      </div>

      <p className="text-[11px] mb-4" style={{ color: "var(--muted)" }}>
        CSV: <code>email,name,employee_code,branch,department,position,unit</code> — <code>unit</code> là tên đơn vị (workspace); bỏ trống → gán vào đơn vị đang chọn. Xem mẫu <code>apps/api/sample_employees.csv</code>.
        Cán bộ chỉ thấy trợ lý của đơn vị mình, cộng các trợ lý được chủ đơn vị khác mở "Toàn ngân hàng"; chưa gán đơn vị → chỉ thấy trợ lý toàn ngân hàng.
        {!isSuper && <> Bạn đang quản lý cán bộ của <strong>{activeWorkspace?.workspace_name}</strong>; cán bộ tạo/nhập ở đây luôn thuộc đơn vị này.</>}
      </p>

      {isSuper && (
        <div className="flex items-center gap-2 mb-3 text-xs" style={{ color: "var(--muted)" }}>
          <span>Đơn vị:</span>
          <select value={filterWs} onChange={(e) => setFilterWs(e.target.value)} data-testid="filter-unit"
            className="text-xs rounded-lg px-2 py-1.5 outline-none" style={inputStyle}>
            <option value="">Tất cả đơn vị</option>
            {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
      )}

      {/* Import result */}
      {importResult && (
        <div className="rounded-xl px-4 py-3 mb-4 text-sm" style={{ background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)", color: "#22c55e" }}>
          ✅ Đã nhập: {importResult.created} tạo mới, {importResult.skipped} bỏ qua (trùng email)
          {importResult.errors.length > 0 && (
            <div className="mt-1 text-xs" style={{ color: "#f59e0b" }}>
              {importResult.errors.map((e, i) => <p key={i}>{e}</p>)}
            </div>
          )}
          <button onClick={() => setImportResult(null)} className="ml-3 text-xs underline">Đóng</button>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-current" style={{ borderTopColor: "transparent", color: "var(--accent)" }} />
        </div>
      ) : employees.length === 0 ? (
        <div className="text-center py-20">
          <h3 className="text-lg font-semibold mb-1" style={{ color: "var(--foreground)" }}>Chưa có cán bộ</h3>
          <p className="text-sm" style={{ color: "var(--muted)" }}>Thêm thủ công hoặc nhập từ file CSV</p>
        </div>
      ) : (
        <div className="rounded-xl overflow-hidden responsive-table-wrap" style={{ border: "1px solid var(--border)" }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: "var(--card)" }}>
                {["Họ tên", "Email", "Mã CB", "Chức danh", "Đơn vị (workspace)", "Phòng / Chi nhánh", "Trạng thái", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-2.5 font-semibold" style={{ color: "var(--muted)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {employees.map((s) => (
                <tr key={s.id} style={{ borderTop: "1px solid var(--border)" }}>
                  <td className="px-4 py-2.5 font-medium" style={{ color: "var(--foreground)" }}>{s.name}</td>
                  <td className="px-4 py-2.5" style={{ color: "var(--foreground)" }}>{s.email}</td>
                  <td className="px-4 py-2.5" style={{ color: "var(--muted)" }}>{s.employee_code || "—"}</td>
                  <td className="px-4 py-2.5" style={{ color: "var(--muted)" }}>{s.position || "—"}</td>
                  <td className="px-4 py-2.5">
                    {isSuper ? (
                      <select value={s.workspace_id || ""} onChange={(e) => handleUnitChange(s, e.target.value)} data-testid={`unit-${s.email}`}
                        className="text-xs rounded-lg px-2 py-1 outline-none max-w-[220px]" style={{ ...inputStyle, color: s.workspace_id ? "var(--foreground)" : "#f59e0b" }}>
                        <option value="">— Chưa gán đơn vị —</option>
                        {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                        {s.workspace_id && !units.some((u) => u.id === s.workspace_id) && <option value={s.workspace_id}>{s.workspace_name || s.workspace_id}</option>}
                      </select>
                    ) : (
                      <span className="text-xs" style={{ color: "var(--foreground)" }} data-testid={`unit-${s.email}`}>{s.workspace_name || "—"}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5" style={{ color: "var(--muted)" }}>{[s.department, s.branch].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="px-4 py-2.5">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold" style={{
                      background: s.is_active ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                      color: s.is_active ? "#22c55e" : "#ef4444",
                    }}>
                      {s.is_active ? (s.must_change_password ? "Mới" : "Hoạt động") : "Vô hiệu"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    {s.is_active && (
                      <button onClick={() => handleDeactivate(s.id)} className="text-xs font-medium" style={{ color: "#ef4444" }}>
                        Vô hiệu hoá
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Modal */}
      {showAdd && (
        <div style={{ position: "fixed", inset: 0, zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)" }}
          onClick={() => setShowAdd(false)}>
          <div onClick={(e) => e.stopPropagation()} className="rounded-2xl p-6" style={{ background: "var(--card)", border: "1px solid var(--border)", width: 480 }}>
            <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--foreground)" }}>Thêm cán bộ</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Email *</label>
                <input value={form.email} onChange={setField("email")} placeholder="canbo@msb-demo.vn" autoFocus
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle} />
              </div>
              <div className="col-span-2">
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Họ tên *</label>
                <input value={form.name} onChange={setField("name")} placeholder="Nguyễn Văn An"
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle} />
              </div>
              <div className="col-span-2">
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Đơn vị (workspace) — quyết định trợ lý nào cán bộ nhìn thấy</label>
                {isSuper ? (
                  <select value={form.workspace_id} onChange={setField("workspace_id")} data-testid="form-unit"
                    className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle}>
                    <option value="">— Chưa gán (chỉ thấy trợ lý toàn ngân hàng) —</option>
                    {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </select>
                ) : (
                  <div className="w-full text-sm rounded-lg px-3 py-2" style={{ ...inputStyle, opacity: 0.8 }} data-testid="form-unit">{activeWorkspace?.workspace_name}</div>
                )}
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Mã cán bộ</label>
                <input value={form.employee_code} onChange={setField("employee_code")} placeholder="MSB01001"
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle} />
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Chức danh</label>
                <select value={form.position} onChange={setField("position")}
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle}>
                  {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Phòng / Khối</label>
                <input value={form.department} onChange={setField("department")} placeholder="Khối KHDN"
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle} />
              </div>
              <div>
                <label className="text-[11px] font-semibold block mb-1" style={{ color: "var(--muted)" }}>Chi nhánh</label>
                <input value={form.branch} onChange={setField("branch")} placeholder="CN Hà Nội"
                  className="w-full text-sm rounded-lg px-3 py-2 outline-none" style={inputStyle} />
              </div>
            </div>
            <p className="text-[10px] mt-3" style={{ color: "var(--muted)" }}>Mật khẩu mặc định: <strong>{DEFAULT_PASSWORD}</strong> — cán bộ phải đổi ở lần đăng nhập đầu.</p>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowAdd(false)} className="rounded-lg px-4 py-2 text-xs font-medium"
                style={{ background: "var(--background)", color: "var(--foreground)", border: "1px solid var(--border)" }}>Huỷ</button>
              <button onClick={handleAdd} disabled={creating || !form.email.trim() || !form.name.trim()}
                className="rounded-lg px-4 py-2 text-xs font-medium"
                style={{ background: "var(--accent)", color: "#fff" }}>{creating ? "..." : "Thêm"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
