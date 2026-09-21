"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { translations, type Locale, type TranslationKey } from "@/lib/i18n/staff";

type Theme = "dark" | "light";

interface StaffSettingsContextType {
  theme: Theme;
  toggleTheme: () => void;
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: TranslationKey) => string;
}

const StaffSettingsContext = createContext<StaffSettingsContextType | null>(null);

const THEME_KEY = "querion-staff-theme";
const LOCALE_KEY = "querion-staff-locale";

export function StaffSettingsProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("light");
  const [locale, setLocaleState] = useState<Locale>("vi");

  // Restore from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(THEME_KEY) as Theme | null;
    if (saved === "light" || saved === "dark") setTheme(saved);
    const savedLocale = localStorage.getItem(LOCALE_KEY) as Locale | null;
    if (savedLocale === "en" || savedLocale === "vi") setLocaleState(savedLocale);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      localStorage.setItem(THEME_KEY, next);
      return next;
    });
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem(LOCALE_KEY, l);
  }, []);

  const t = useCallback(
    (key: TranslationKey) => translations[locale][key] || key,
    [locale],
  );

  return (
    <StaffSettingsContext.Provider value={{ theme, toggleTheme, locale, setLocale, t }}>
      {children}
    </StaffSettingsContext.Provider>
  );
}

export function useStaffSettings() {
  const ctx = useContext(StaffSettingsContext);
  if (!ctx) throw new Error("useStaffSettings must be within StaffSettingsProvider");
  return ctx;
}

// Theme CSS variables — warm orange accent on navy/white (bank branding)
export function getThemeVars(theme: Theme) {
  if (theme === "light") {
    return {
      "--s-bg": "#f7f7f9",
      "--s-bg-secondary": "#ffffff",
      "--s-bg-tertiary": "#f1f2f5",
      "--s-bg-hover": "#e8e9ee",
      "--s-border": "rgba(15,23,42,0.08)",
      "--s-text": "#0f172a",
      "--s-text-secondary": "#475569",
      "--s-text-muted": "#94a3b8",
      "--s-accent": "#ee6d1f",
      "--s-accent-light": "rgba(238,109,31,0.10)",
      "--s-accent-text": "#c9560f",
      "--s-user-bubble": "rgba(238,109,31,0.12)",
      "--s-user-text": "#9a4410",
      "--s-bot-bubble": "#ffffff",
      "--s-bot-text": "#1e293b",
      "--s-input-bg": "#ffffff",
      "--s-input-border": "rgba(15,23,42,0.12)",
    };
  }
  return {
    "--s-bg": "#0b1220",
    "--s-bg-secondary": "#111a2e",
    "--s-bg-tertiary": "rgba(255,255,255,0.03)",
    "--s-bg-hover": "rgba(255,255,255,0.06)",
    "--s-border": "rgba(255,255,255,0.07)",
    "--s-text": "#f1f5f9",
    "--s-text-secondary": "#94a3b8",
    "--s-text-muted": "#64748b",
    "--s-accent": "#ff8a4c",
    "--s-accent-light": "rgba(255,138,76,0.15)",
    "--s-accent-text": "#ffb98a",
    "--s-user-bubble": "rgba(255,138,76,0.18)",
    "--s-user-text": "#ffd1b3",
    "--s-bot-bubble": "rgba(255,255,255,0.05)",
    "--s-bot-text": "#e2e8f0",
    "--s-input-bg": "rgba(255,255,255,0.05)",
    "--s-input-border": "rgba(255,255,255,0.1)",
  };
}
