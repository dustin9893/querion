"use client";

import { useAuth, useWorkspace } from "@/components/providers/AuthProvider";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import OpsBubble from "@/components/ops/OpsBubble";

/**
 * Shell that conditionally renders sidebar+topbar when authenticated.
 * Login page always renders immediately without waiting for auth.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const { activeWorkspace } = useWorkspace();
  const pathname = usePathname();

  // Login + staff/customer portal pages — render immediately, no sidebar/topbar
  if (pathname === "/login" || pathname.startsWith("/staff") || pathname.startsWith("/kh") || pathname.startsWith("/embed")) {
    return <>{children}</>;
  }

  // Other pages — show loading while checking auth
  if (loading) {
    return (
      <div
        className="flex h-screen items-center justify-center"
        style={{ background: "var(--background)" }}
      >
        <div
          className="animate-pulse flex items-center gap-3"
          style={{ color: "var(--muted)" }}
        >
          <div
            className="rounded-lg"
            style={{
              width: 40,
              height: 40,
              background: "linear-gradient(135deg, var(--accent) 0%, #a855f7 100%)",
            }}
          />
          <span className="text-lg font-semibold">Loading...</span>
        </div>
      </div>
    );
  }

  // Not authenticated on non-login pages — render children (redirect handled by AuthProvider)
  if (!isAuthenticated) {
    return <>{children}</>;
  }

  const closeMobileSidebar = () => {
    document.getElementById("sidebar")?.classList.remove("open");
    document.getElementById("sidebar-overlay")?.classList.remove("open");
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      {/* Mobile overlay — closes sidebar when tapped */}
      <div id="sidebar-overlay" onClick={closeMobileSidebar} />
      <div
        id="main-content"
        className="flex flex-1 flex-col overflow-hidden"
        style={{ marginLeft: "var(--sidebar-width)" }}
      >
        <Topbar />
        <main key={activeWorkspace?.workspace_id || "none"} className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
      {/* Trợ lý Vận hành: một chỗ gắn duy nhất cho mọi trang quản trị. Nó tự ẩn ở các trang
          không phù hợp và khi super admin tắt tính năng. */}
      <OpsBubble />
    </div>
  );
}
