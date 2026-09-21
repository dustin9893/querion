"use client";

import { useWorkspace, useAuth, type WorkspaceMembership } from "@/components/providers/AuthProvider";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";

const roleBadgeColors: Record<string, string> = {
  owner: "#22c55e",
  editor: "#3b82f6",
  viewer: "#a855f7",
};

export default function WorkspaceSwitcher() {
  const { activeWorkspace, workspaces, switchWorkspace } = useWorkspace();
  const { isSuper, user } = useAuth();
  const [open, setOpen] = useState(false);
  const [allWorkspaces, setAllWorkspaces] = useState<WorkspaceMembership[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Super admin: fetch all workspaces on open
  useEffect(() => {
    if (open && isSuper) {
      api
        .get<{ id: string; name: string }[]>("/v1/workspaces")
        .then((wsList) => {
          setAllWorkspaces(
            wsList.map((ws) => ({
              workspace_id: ws.id,
              workspace_name: ws.name,
              ws_role: "owner" as const,
            })),
          );
        })
        .catch(() => {});
    }
  }, [open, isSuper]);

  const displayWorkspaces = isSuper ? allWorkspaces : workspaces;
  const displayName = activeWorkspace?.workspace_name || "Select workspace";
  const displayRole = activeWorkspace?.ws_role;

  return (
    <div ref={ref} className="relative">
      <button
        id="workspace-selector"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-all duration-200"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          color: "var(--muted)",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--accent)"; }}
        onMouseLeave={(e) => { if (!open) e.currentTarget.style.borderColor = "var(--border)"; }}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M2 4L8 2L14 4V12L8 14L2 12V4Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
          <path d="M8 7V14" stroke="currentColor" strokeWidth="1.2"/>
          <path d="M2 4L8 7L14 4" stroke="currentColor" strokeWidth="1.2"/>
        </svg>
        <span className="max-w-[150px] truncate">{displayName}</span>
        {displayRole && !isSuper && (
          <span
            className="text-xs px-1.5 py-0.5 rounded font-medium"
            style={{
              background: `${roleBadgeColors[displayRole]}20`,
              color: roleBadgeColors[displayRole],
            }}
          >
            {displayRole}
          </span>
        )}
        {isSuper && (
          <span
            className="text-xs px-1.5 py-0.5 rounded font-medium"
            style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444" }}
          >
            super
          </span>
        )}
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none"
          className="transition-transform duration-200"
          style={{ transform: open ? "rotate(180deg)" : "none" }}
        >
          <path d="M3 5L6 8L9 5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-1 rounded-lg py-1 shadow-xl z-50"
          style={{
            background: "var(--card)",
            border: "1px solid var(--border)",
            minWidth: 240,
            maxHeight: 300,
            overflowY: "auto",
          }}
        >
          {displayWorkspaces.length === 0 && (
            <p className="px-3 py-2 text-xs" style={{ color: "var(--muted)" }}>
              No workspaces available
            </p>
          )}
          {displayWorkspaces.map((ws) => {
            const isActive = ws.workspace_id === activeWorkspace?.workspace_id;
            return (
              <button
                key={ws.workspace_id}
                onClick={() => {
                  switchWorkspace(ws.workspace_id, ws.workspace_name);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between px-3 py-2 text-sm transition-colors duration-150"
                style={{
                  color: isActive ? "var(--accent-hover)" : "var(--foreground)",
                  background: isActive ? "var(--accent-glow)" : "transparent",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.background = "var(--card-hover)";
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.background = "transparent";
                }}
              >
                <span className="truncate">{ws.workspace_name}</span>
                {!isSuper && (
                  <span
                    className="text-xs px-1.5 py-0.5 rounded font-medium ml-2 flex-shrink-0"
                    style={{
                      background: `${roleBadgeColors[ws.ws_role]}20`,
                      color: roleBadgeColors[ws.ws_role],
                    }}
                  >
                    {ws.ws_role}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
