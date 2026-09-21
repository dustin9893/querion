"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import { api, setAccessToken, setActiveWorkspaceId } from "@/lib/api";

// ---------- Types ----------
export interface WorkspaceMembership {
  workspace_id: string;
  workspace_name: string;
  ws_role: "owner" | "editor" | "viewer";
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: "super_admin" | "admin";
  workspaces: WorkspaceMembership[];
}

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
  isSuper: boolean;
}

interface WorkspaceContextType {
  activeWorkspace: WorkspaceMembership | null;
  wsRole: "owner" | "editor" | "viewer" | null;
  workspaces: WorkspaceMembership[];
  switchWorkspace: (workspaceId: string, workspaceName?: string) => void;
}

interface PermissionContextType {
  canEdit: boolean;
  canManageMembers: boolean;
  isOwner: boolean;
  isViewer: boolean;
  isSuper: boolean;
}

// ---------- Contexts ----------
const AuthContext = createContext<AuthContextType | null>(null);
const WorkspaceContext = createContext<WorkspaceContextType | null>(null);
const PermissionContext = createContext<PermissionContextType | null>(null);

const TOKEN_KEY = "querion-refresh-token";
const WS_KEY = "querion-active-ws";
const WS_NAME_KEY = "querion-active-ws-name";

/**
 * A super admin is usually not a formal member of any unit, so `me.workspaces` is empty and
 * nothing would set the X-Workspace-Id header — every unit-scoped page then fails with
 * "Chưa chọn đơn vị". Pick the first unit automatically; the switcher can change it later.
 */
async function firstWorkspaceForSuperAdmin(): Promise<WorkspaceMembership | null> {
  try {
    const list = await api.get<{ id: string; name: string }[]>("/v1/workspaces");
    const ws = list[0];
    return ws ? { workspace_id: ws.id, workspace_name: ws.name, ws_role: "owner" } : null;
  } catch {
    return null;
  }
}

// ---------- Provider ----------
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeWsId, setActiveWsId] = useState<string | null>(null);
  const [superWsOverride, setSuperWsOverride] = useState<WorkspaceMembership | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const redirectedRef = useRef(false);

  // Restore session on mount (client-only)
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      try {
        const refreshToken = localStorage.getItem(TOKEN_KEY);
        if (!refreshToken) {
          return; // no token, remain unauthenticated
        }

        const data = await api.post<{ access_token: string }>("/v1/auth/refresh", {
          refresh_token: refreshToken,
        });
        if (cancelled) return;

        setAccessToken(data.access_token);
        const me = await api.get<AuthUser>("/v1/auth/me");
        if (cancelled) return;

        setUser(me);

        // Restore active workspace
        const savedWs = localStorage.getItem(WS_KEY);
        if (savedWs && me.workspaces.some((w) => w.workspace_id === savedWs)) {
          setActiveWsId(savedWs);
          setActiveWorkspaceId(savedWs);
        } else if (savedWs && me.role === "super_admin") {
          // Super admin might not be a formal member — restore from saved name
          setActiveWsId(savedWs);
          setActiveWorkspaceId(savedWs);
          const savedName = localStorage.getItem(WS_NAME_KEY) || "Workspace";
          setSuperWsOverride({ workspace_id: savedWs, workspace_name: savedName, ws_role: "owner" });
        } else if (me.workspaces.length > 0) {
          setActiveWsId(me.workspaces[0].workspace_id);
          setActiveWorkspaceId(me.workspaces[0].workspace_id);
        } else if (me.role === "super_admin") {
          const ws = await firstWorkspaceForSuperAdmin();
          if (cancelled) return;
          if (ws) {
            setActiveWsId(ws.workspace_id);
            setActiveWorkspaceId(ws.workspace_id);
            setSuperWsOverride(ws);
            localStorage.setItem(WS_KEY, ws.workspace_id);
            localStorage.setItem(WS_NAME_KEY, ws.workspace_name);
          }
        }
      } catch {
        // Token invalid/expired — clear it
        localStorage.removeItem(TOKEN_KEY);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restore();
    return () => { cancelled = true; };
  }, []);

  // Redirect logic — only fires ONCE after loading completes
  useEffect(() => {
    if (loading) return;
    if (redirectedRef.current) return;

    // Skip admin auth checks for staff / public customer routes — they have their own auth
    if (pathname.startsWith("/staff") || pathname.startsWith("/kh") || pathname.startsWith("/embed")) return;

    if (!user && pathname !== "/login") {
      redirectedRef.current = true;
      router.replace("/login");
    } else if (user && pathname === "/login") {
      redirectedRef.current = true;
      router.replace("/datasets");
    }
  }, [user, loading, pathname, router]);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await api.post<{
        access_token: string;
        refresh_token: string;
        user: AuthUser;
      }>("/v1/auth/login", { email, password });

      setAccessToken(data.access_token);
      localStorage.setItem(TOKEN_KEY, data.refresh_token);

      // Auto-select first workspace (super admin: first unit in the system) BEFORE setUser:
      // setting the user triggers the redirect to /datasets, and that page's first requests
      // must already carry X-Workspace-Id (otherwise they fail with "Chưa chọn đơn vị").
      if (data.user.workspaces.length > 0) {
        const wsId = data.user.workspaces[0].workspace_id;
        setActiveWsId(wsId);
        setActiveWorkspaceId(wsId);
        localStorage.setItem(WS_KEY, wsId);
      } else if (data.user.role === "super_admin") {
        const ws = await firstWorkspaceForSuperAdmin();
        if (ws) {
          setActiveWsId(ws.workspace_id);
          setActiveWorkspaceId(ws.workspace_id);
          setSuperWsOverride(ws);
          localStorage.setItem(WS_KEY, ws.workspace_id);
          localStorage.setItem(WS_NAME_KEY, ws.workspace_name);
        }
      }
      setUser(data.user);

      router.replace("/datasets");
    },
    [router],
  );

  const logout = useCallback(() => {
    setAccessToken(null);
    setActiveWorkspaceId(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(WS_KEY);
    setUser(null);
    setActiveWsId(null);
    redirectedRef.current = false;
    // Hard redirect to ensure page navigates reliably
    window.location.href = "/login";
  }, []);

  const switchWorkspace = useCallback(
    (workspaceId: string, workspaceName?: string) => {
      setActiveWsId(workspaceId);
      setActiveWorkspaceId(workspaceId);
      localStorage.setItem(WS_KEY, workspaceId);
      // For super_admin selecting a workspace they're not a member of
      if (workspaceName) {
        setSuperWsOverride({ workspace_id: workspaceId, workspace_name: workspaceName, ws_role: "owner" });
        localStorage.setItem(WS_NAME_KEY, workspaceName);
      }
    },
    [],
  );

  // Derived values
  const isSuper = user?.role === "super_admin";
  const activeWorkspace =
    user?.workspaces.find((w) => w.workspace_id === activeWsId)
    ?? (isSuper ? superWsOverride : null);
  const wsRole = activeWorkspace?.ws_role ?? null;

  const permissions: PermissionContextType = {
    canEdit: isSuper || wsRole === "owner" || wsRole === "editor",
    canManageMembers: isSuper || wsRole === "owner",
    isOwner: isSuper || wsRole === "owner",
    isViewer: wsRole === "viewer",
    isSuper,
  };

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, isAuthenticated: !!user, isSuper }}
    >
      <WorkspaceContext.Provider
        value={{
          activeWorkspace,
          wsRole,
          workspaces: user?.workspaces ?? [],
          switchWorkspace,
        }}
      >
        <PermissionContext.Provider value={permissions}>
          {children}
        </PermissionContext.Provider>
      </WorkspaceContext.Provider>
    </AuthContext.Provider>
  );
}

// ---------- Hooks ----------
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be within AuthProvider");
  return ctx;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be within AuthProvider");
  return ctx;
}

export function usePermission() {
  const ctx = useContext(PermissionContext);
  if (!ctx) throw new Error("usePermission must be within AuthProvider");
  return ctx;
}
