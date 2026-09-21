"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/components/providers/I18nProvider";
import { useAuth, usePermission } from "@/components/providers/AuthProvider";
import { BRAND_NAME } from "@/lib/brand";

const navItems = [
  {
    labelKey: "nav.datasets",
    href: "/datasets",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 5C3 3.89543 3.89543 3 5 3H15C16.1046 3 17 3.89543 17 5V7C17 8.10457 16.1046 9 15 9H5C3.89543 9 3 8.10457 3 7V5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M3 13C3 11.8954 3.89543 11 5 11H15C16.1046 11 17 11.8954 17 13V15C17 16.1046 16.1046 17 15 17H5C3.89543 17 3 16.1046 3 15V13Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx="6" cy="6" r="1" fill="currentColor"/>
        <circle cx="6" cy="14" r="1" fill="currentColor"/>
      </svg>
    ),
  },
  {
    labelKey: "nav.workflows",
    href: "/workflows",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 4H8V8H4V4Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M12 12H16V16H12V12Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M8 6H12V6C12 8.20914 10.2091 10 8 10V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M8 10V14H12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    labelKey: "nav.apps",
    href: "/apps",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="11" y="3" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="3" y="11" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="11" y="11" width="6" height="6" rx="3" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ),
  },
  {
    labelKey: "nav.tools",
    href: "/tools",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12.6 2.8a4 4 0 0 0-5 5L3 12.4a1.5 1.5 0 0 0 0 2.1l2.5 2.5a1.5 1.5 0 0 0 2.1 0l4.6-4.6a4 4 0 0 0 5-5l-2.4 2.4-2.1-.5-.5-2.1 2.4-2.4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    labelKey: "nav.skills",
    href: "/skills",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5"/>
        <circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="1.5"/>
        <circle cx="10" cy="10" r="0.8" fill="currentColor"/>
      </svg>
    ),
  },
  {
    labelKey: "nav.forms",
    href: "/forms",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 3H12L16 7V17H5V3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M11.5 3V7.5H16" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M7.5 11H13M7.5 14H11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    labelKey: "nav.chat",
    href: "/chat",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 4H16C16.5523 4 17 4.44772 17 5V13C17 13.5523 16.5523 14 16 14H7L4 17V5C4 4.44772 4.44772 4 5 4H4Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M7 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M7 11H10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
];

const adminItems = [
  {
    labelKey: "admin.users",
    href: "/admin/users",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="7" r="3" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M4 17C4 14.2386 6.68629 12 10 12C13.3137 12 16 14.2386 16 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.workspaces",
    href: "/admin/workspaces",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M3 6L10 3L17 6V14L10 17L3 14V6Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M10 10V17" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M3 6L10 10L17 6" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.settings",
    href: "/admin/settings",
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M10 2V4M10 16V18M2 10H4M16 10H18M4.22 4.22L5.64 5.64M14.36 14.36L15.78 15.78M4.22 15.78L5.64 14.36M14.36 5.64L15.78 4.22" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.ops",
    href: "/admin/ops",
    // không có ownerOk: chỉ super admin cấu hình được trợ lý vận hành
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M10 2.5l6 3.2v4.1c0 3.4-2.4 6.2-6 7.7-3.6-1.5-6-4.3-6-7.7V5.7l6-3.2z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M7.8 9.5h4.4M7.8 12h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.audit",
    href: "/admin/audit",
    ownerOk: true, // the audit API already limits admins to units they own
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M5 3H13L16 6V17H5V3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M8 9H13M8 12H13M8 15H11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.schedules",
    href: "/admin/schedules",
    ownerOk: true, // schedules belong to a unit, like its workflows
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M10 6V10L12.5 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.usage",
    href: "/admin/usage",
    ownerOk: true, // the usage API limits admins to units they own, like the audit log
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M3 17H17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M5.5 14V10M10 14V5M14.5 14V8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
      </svg>
    ),
  },
  {
    labelKey: "admin.employees",
    href: "/admin/employees",
    ownerOk: true, // unit admins manage the staff of their own unit
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <path d="M10 3L17 7V9L10 13L3 9V7L10 3Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M5 10V14L10 17L15 14V10" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
      </svg>
    ),
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { t } = useI18n();
  const { isSuper, logout, user } = useAuth();
  const { isOwner } = usePermission(); // owner of the active unit (or super admin)
  const visibleAdminItems = adminItems.filter((item) => isSuper || ("ownerOk" in item && item.ownerOk));

  return (
    <aside
      id="sidebar"
      className="fixed left-0 top-0 z-40 h-screen flex flex-col border-r"
      style={{
        width: "var(--sidebar-width)",
        background: "var(--card)",
        borderColor: "var(--border)",
      }}
    >
      {/* Logo */}
      <div
        className="flex items-center gap-3 px-5 font-semibold text-lg tracking-tight"
        style={{ height: "var(--topbar-height)", borderBottom: "1px solid var(--border)" }}
      >
        <Image src="/icon.png" alt={BRAND_NAME} width={32} height={32} className="rounded-lg" />
        <span className="text-base leading-tight" style={{ color: "var(--foreground)" }}>{BRAND_NAME}</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="flex flex-col gap-1">
          {navItems.map((item) => {
            const isActive = pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  id={`nav-${item.labelKey.split(".")[1]}`}
                  className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200"
                  style={{
                    color: isActive ? "var(--accent-hover)" : "var(--muted)",
                    background: isActive ? "var(--accent-glow)" : "transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) { e.currentTarget.style.color = "var(--foreground)"; e.currentTarget.style.background = "var(--card-hover)"; }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.background = "transparent"; }
                  }}
                >
                  {item.icon}
                  {t(item.labelKey)}
                </Link>
              </li>
            );
          })}
        </ul>

        {/* Admin section — super admin sees everything; a unit owner sees staff + audit */}
        {(isSuper || (isOwner && visibleAdminItems.length > 0)) && (
          <>
            <div className="mt-6 mb-2 px-3">
              <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
                {t("admin.section")}
              </span>
            </div>
            <ul className="flex flex-col gap-1">
              {visibleAdminItems.map((item) => {
                const isActive = pathname.startsWith(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200"
                      style={{
                        color: isActive ? "var(--accent-hover)" : "var(--muted)",
                        background: isActive ? "var(--accent-glow)" : "transparent",
                      }}
                      onMouseEnter={(e) => {
                        if (!isActive) { e.currentTarget.style.color = "var(--foreground)"; e.currentTarget.style.background = "var(--card-hover)"; }
                      }}
                      onMouseLeave={(e) => {
                        if (!isActive) { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.background = "transparent"; }
                      }}
                    >
                      {item.icon}
                      {t(item.labelKey)}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </nav>

      {/* Footer — User info + Logout */}
      <div
        className="px-4 py-3 flex items-center justify-between"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div
            className="flex-shrink-0 flex items-center justify-center rounded-full text-xs font-bold"
            style={{
              width: 28, height: 28,
              background: "linear-gradient(135deg, var(--accent) 0%, #f59e0b 100%)",
              color: "#fff",
            }}
          >
            {user?.name?.[0]?.toUpperCase() || "U"}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: "var(--foreground)" }}>
              {user?.name}
            </p>
            <p className="text-xs truncate" style={{ color: "var(--muted)" }}>
              {user?.role === "super_admin" ? "Quản trị hệ thống" : "Quản trị đơn vị"}
            </p>
          </div>
        </div>
        <button
          onClick={logout}
          className="flex-shrink-0 rounded-lg p-2 transition-all duration-200"
          style={{ color: "var(--muted)" }}
          onMouseEnter={(e) => { e.currentTarget.style.color = "#ef4444"; e.currentTarget.style.background = "rgba(239,68,68,0.1)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.background = "transparent"; }}
          title="Logout"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M7 16H3C2.44772 16 2 15.5523 2 15V3C2 2.44772 2.44772 2 3 2H7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <path d="M12 12L16 9L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M6 9H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </button>
      </div>
    </aside>
  );
}
