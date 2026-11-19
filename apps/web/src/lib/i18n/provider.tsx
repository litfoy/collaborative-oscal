// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { createI18n } from ".";
import { LOCALE_COOKIE, LOCALE_MAX_AGE, type Locale } from "./locale";

const LocaleContext = createContext<{
  locale: Locale;
  setLocale: (locale: Locale) => void;
}>({ locale: "en", setLocale: () => { throw new Error("Missing LocaleProvider"); } });

export function LocaleProvider({ locale: initialLocale, children }: { locale: Locale; children: ReactNode }) {
  const [selectedLocale, setSelectedLocale] = useState(initialLocale);
  const locale = selectedLocale;

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const context = useMemo(() => ({
    locale,
    setLocale: (next: Locale) => {
      document.cookie = `${LOCALE_COOKIE}=${next}; Path=/; Max-Age=${LOCALE_MAX_AGE}; SameSite=Lax${location.protocol === "https:" ? "; Secure" : ""}`;
      setSelectedLocale(next);
    },
  }), [locale]);

  return <LocaleContext.Provider value={context}>{children}</LocaleContext.Provider>;
}

export function useI18n() {
  const { locale } = useContext(LocaleContext);
  return useMemo(() => createI18n(locale), [locale]);
}

export function useLocalePreference() {
  return useContext(LocaleContext);
}
