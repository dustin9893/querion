"use client";

import { useAuth } from "@/components/providers/AuthProvider";
import { useI18n } from "@/components/providers/I18nProvider";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

interface WorkspaceItem {
  id: string;
  name: string;
  created_at: string;
  member_count: number;
}

interface UserItem { id: string; email: string; name: string; role: string; }

export default function AdminWorkspacesPage() {
  const { isSuper } = useAuth();
  const { t } = useI18n();
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", owner_user_id: "" });
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const fetchAll = async () => {
    try {
      const [ws, us] = await Promise.all([
        api.get<WorkspaceItem[]>("/v1/workspaces"),
        api.get<UserItem[]>("/v1/users"),
      ]);
      setWorkspaces(ws);
      setUsers(us.filter((u) => u.role === "admin"));
    } catch {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      await api.post("/v1/workspaces", form);
      setShowCreate(false);
      setForm({ name: "", owner_user_id: "" });
      fetchAll();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!deleteTarget) return;
    await api.delete(`/v1/workspaces/${deleteTarget}`);
    setDeleteTarget(null);
    fetchAll();
  };

  if (!isSuper) {
    return (
      <div className="flex items-center justify-center h-64">
        <p style={{ color: "var(--muted)" }}>Access denied. Super admin only.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold" style={{ color: "var(--foreground)" }}>
            Workspaces Management
          </h2>
          <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
            Create and manage workspaces
          </p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white"
          style={{ background: "var(--accent)" }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          {t("buttons.create")} Workspace
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate}
          className="rounded-xl p-4 mb-6 flex flex-wrap gap-3 items-end"
          style={{ background: "var(--card)", border: "1px solid var(--border)" }}>
          {error && <p className="w-full text-sm" style={{ color: "#ef4444" }}>{error}</p>}
          <input type="text" placeholder="Workspace name" required value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="flex-1 min-w-[200px] rounded-lg px-3 py-2 text-sm outline-none"
            style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}
          />
          <select value={form.owner_user_id} required
            onChange={(e) => setForm({ ...form, owner_user_id: e.target.value })}
            className="flex-1 min-w-[200px] rounded-lg px-3 py-2 text-sm outline-none"
            style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }}>
            <option value="">Select owner...</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
            ))}
          </select>
          <button type="submit" className="rounded-lg px-4 py-2 text-sm font-medium text-white" style={{ background: "var(--accent)" }}>
            {t("buttons.create")}
          </button>
          <button type="button" onClick={() => setShowCreate(false)} className="rounded-lg px-4 py-2 text-sm" style={{ color: "var(--muted)" }}>
            {t("buttons.cancel")}
          </button>
        </form>
      )}

      <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
        {workspaces.map((ws) => (
          <div key={ws.id} className="rounded-xl p-5 transition-all duration-200"
            style={{ background: "var(--card)", border: "1px solid var(--border)" }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold" style={{ color: "var(--foreground)" }}>{ws.name}</h3>
              <button onClick={() => setDeleteTarget(ws.id)} className="text-xs px-2 py-1 rounded"
                style={{ color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}>
                {t("buttons.delete")}
              </button>
            </div>
            <div className="flex gap-3 text-xs" style={{ color: "var(--muted)" }}>
              <span>{ws.member_count} members</span>
              <span>Created {new Date(ws.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
      {loading && <p className="p-4 text-sm" style={{ color: "var(--muted)" }}>Loading...</p>}
      {!loading && workspaces.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl py-16"
          style={{ border: "1px dashed var(--border)", background: "var(--card)" }}>
          <p className="text-sm" style={{ color: "var(--muted)" }}>No workspaces yet</p>
        </div>
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        message="Are you sure you want to delete this workspace?"
        variant="danger"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
