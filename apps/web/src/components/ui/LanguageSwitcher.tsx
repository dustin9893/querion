"use client";

import { useI18n, type Locale } from "@/components/providers/I18nProvider";
import { useState, useRef, useEffect } from "react";

const locales: { code: Locale; label: string; flag: string }[] = [
  { code: "en", label: "EN", flag: "🇺🇸" },
  { code: "vi", label: "VI", flag: "🇻🇳" },
];

export default function LanguageSwitcher() {
  const { locale, setLocale } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const current = locales.find((l) => l.code === locale) || locales[0];

  return (
    <div ref={ref} className="relative">
      <button
        id="language-switcher"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm transition-all duration-200"
        style={{
          background: "var(--card)",
          border: "1px solid var(--border)",
          color: "var(--muted)",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "var(--accent)";
          e.currentTarget.style.color = "var(--foreground)";
        }}
        onMouseLeave={(e) => {
          if (!open) {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--muted)";
          }
        }}
      >
        <span>{current.flag}</span>
        <span className="font-medium">{current.label}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className="transition-transform duration-200"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
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
            minWidth: 120,
          }}
        >
          {locales.map((l) => (
            <button
              key={l.code}
              id={`lang-${l.code}`}
              onClick={() => {
                setLocale(l.code);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors duration-150"
              style={{
                color: l.code === locale ? "var(--accent-hover)" : "var(--foreground)",
                background: l.code === locale ? "var(--accent-glow)" : "transparent",
              }}
              onMouseEnter={(e) => {
                if (l.code !== locale) {
                  e.currentTarget.style.background = "var(--card-hover)";
                }
              }}
              onMouseLeave={(e) => {
                if (l.code !== locale) {
                  e.currentTarget.style.background = "transparent";
                }
              }}
            >
              <span>{l.flag}</span>
              <span>{l.code === "en" ? "English" : "Tiếng Việt"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
