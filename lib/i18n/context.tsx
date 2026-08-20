"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";
import { supportedLocales, translations, type SupportedLocale, type TranslationKey } from "@/lib/i18n/translations";

type I18nContextValue = {
  locale: SupportedLocale;
  setLocale: (locale: SupportedLocale) => void;
  t: (key: TranslationKey, params?: Record<string, string | number>) => string;
  locales: readonly SupportedLocale[];
};

const I18N_STORAGE_KEY = "amf-locale";
const I18N_CHANGE_EVENT = "amf-locale-change";

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore<SupportedLocale>(subscribeLocale, getClientLocaleSnapshot, getServerLocaleSnapshot);

  const setLocale = useCallback((nextLocale: SupportedLocale) => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(I18N_STORAGE_KEY, nextLocale);
    document.documentElement.lang = nextLocale;
    window.dispatchEvent(new Event(I18N_CHANGE_EVENT));
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nContextValue>(() => {
    return {
      locale,
      setLocale,
      locales: supportedLocales,
      t: (key, params) => translate(locale, key, params),
    };
  }, [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used inside I18nProvider");
  }
  return context;
}

export type TranslateFunction = I18nContextValue["t"];

function isSupportedLocale(locale: string): locale is SupportedLocale {
  return supportedLocales.includes(locale as SupportedLocale);
}

function matchBrowserLocale(browserLang: string): SupportedLocale {
  const normalized = browserLang.toLowerCase();
  if (normalized.startsWith("zh")) return "zh-Hant";
  if (normalized.startsWith("ja")) return "ja";
  return "en";
}

function getInitialLocale(): SupportedLocale {
  if (typeof window === "undefined") return "en";

  const stored = window.localStorage.getItem(I18N_STORAGE_KEY);
  if (stored && isSupportedLocale(stored)) return stored;

  return matchBrowserLocale(navigator.language);
}

function getClientLocaleSnapshot(): SupportedLocale {
  return getInitialLocale();
}

function getServerLocaleSnapshot(): SupportedLocale {
  return "en";
}

function subscribeLocale(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};

  const handler = () => callback();
  window.addEventListener("storage", handler);
  window.addEventListener(I18N_CHANGE_EVENT, handler);

  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener(I18N_CHANGE_EVENT, handler);
  };
}

function translate(locale: SupportedLocale, key: TranslationKey, params?: Record<string, string | number>) {
  const path = key.split(".");
  let current: unknown = translations[locale];
  for (const segment of path) {
    if (!current || typeof current !== "object" || !(segment in current)) {
      return key;
    }
    current = (current as Record<string, unknown>)[segment];
  }

  if (typeof current !== "string") return key;

  if (!params) return current;
  return Object.entries(params).reduce((acc, [paramKey, value]) => {
    return acc.replaceAll(`{${paramKey}}`, String(value));
  }, current);
}
