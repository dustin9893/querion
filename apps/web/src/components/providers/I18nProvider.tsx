"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

// Import all translation files statically
import enCommon from "@/locales/en/common.json";
import enDatasets from "@/locales/en/datasets.json";
import enWorkflows from "@/locales/en/workflows.json";
import enApps from "@/locales/en/apps.json";
import enChat from "@/locales/en/chat.json";

import viCommon from "@/locales/vi/common.json";
import viDatasets from "@/locales/vi/datasets.json";
import viWorkflows from "@/locales/vi/workflows.json";
import viApps from "@/locales/vi/apps.json";
import viChat from "@/locales/vi/chat.json";

export type Locale = "en" | "vi";

type Messages = Record<string, Record<string, unknown>>;

const messages: Record<Locale, Messages> = {
  en: { common: enCommon, datasets: enDatasets, workflows: enWorkflows, apps: enApps, chat: enChat },
  vi: { common: viCommon, datasets: viDatasets, workflows: viWorkflows, apps: viApps, chat: viChat },
};

interface I18nContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, namespace?: string) => string;
}

const I18nContext = createContext<I18nContextType | null>(null);

/**
 * Resolve a dot-notation key from a nested object.
 * e.g. t("nav.datasets", "common") → messages[locale].common.nav.datasets
 */
function resolve(obj: unknown, path: string): string {
  const parts = path.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return path;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : path;
}

const STORAGE_KEY = "querion-locale";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("vi");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as Locale | null;
    if (saved && (saved === "en" || saved === "vi")) {
      setLocaleState(saved);
    }
    setMounted(true);
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem(STORAGE_KEY, newLocale);
    document.documentElement.lang = newLocale;
  }, []);

  const t = useCallback(
    (key: string, namespace: string = "common") => {
      const ns = messages[locale]?.[namespace];
      if (!ns) return key;
      return resolve(ns, key);
    },
    [locale],
  );

  // Avoid hydration mismatch
  if (!mounted) {
    const t = (key: string, namespace: string = "common") => {
      const ns = messages["vi"]?.[namespace];
      if (!ns) return key;
      return resolve(ns, key);
    };
    return (
      <I18nContext.Provider value={{ locale: "vi", setLocale, t }}>
        {children}
      </I18nContext.Provider>
    );
  }

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
