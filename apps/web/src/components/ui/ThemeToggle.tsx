"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <button
        className="flex items-center justify-center rounded-lg"
        style={{ width: 36, height: 36, background: "var(--card)", border: "1px solid var(--border)" }}
      >
        <div style={{ width: 18, height: 18 }} />
      </button>
    );
  }

  const cycleTheme = () => {
    if (theme === "dark") setTheme("light");
    else if (theme === "light") setTheme("system");
    else setTheme("dark");
  };

  return (
    <button
      id="theme-toggle"
      onClick={cycleTheme}
      className="flex items-center justify-center rounded-lg transition-all duration-200"
      style={{
        width: 36,
        height: 36,
        background: "var(--card)",
        border: "1px solid var(--border)",
        color: "var(--muted)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--accent)";
        e.currentTarget.style.color = "var(--foreground)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border)";
        e.currentTarget.style.color = "var(--muted)";
      }}
      title={`Theme: ${theme}`}
    >
      {theme === "dark" && (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M15.5 9.5C14.5 13 11 15 7.5 14C4 13 2 9.5 3 6C1.5 7 1 9.5 1.5 12C2.3 15.4 5.7 17.5 9.1 16.7C12.5 15.9 14.6 12.5 14 9C14.8 9.3 15.2 9.4 15.5 9.5Z" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      )}
      {theme === "light" && (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="9" cy="9" r="3.5" stroke="currentColor" strokeWidth="1.3"/>
          <path d="M9 2V3.5M9 14.5V16M2 9H3.5M14.5 9H16M4.05 4.05L5.1 5.1M12.9 12.9L13.95 13.95M13.95 4.05L12.9 5.1M5.1 12.9L4.05 13.95" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
        </svg>
      )}
      {theme === "system" && (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="2" y="3" width="14" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
          <path d="M6 16H12M9 13V16" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
        </svg>
      )}
    </button>
  );
}
