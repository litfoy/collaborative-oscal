// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { resolveLocale } from "@/lib/i18n/locale";
import { useI18n, useLocalePreference } from "@/lib/i18n/provider";

export function LanguageSelector() {
  const { t } = useI18n();
  const { locale, setLocale } = useLocalePreference();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return (
    <label className="language-selector">
      <span>{t("common.language")}</span>
      <select value={locale} aria-label={t("common.language")} aria-busy={pending} onChange={(event) => {
        setLocale(resolveLocale(event.target.value));
        startTransition(() => router.refresh());
      }}>
        <option value="en" lang="en">English</option>
        <option value="de" lang="de">Deutsch</option>
      </select>
    </label>
  );
}
