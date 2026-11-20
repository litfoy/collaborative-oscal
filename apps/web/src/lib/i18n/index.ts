// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiError, ERROR_MESSAGES, ERROR_TRANSLATION_KEYS } from "@/lib/errors";

import * as common from "./common";
import * as assessmentPlans from "./assessment-plans";
import * as assessmentResults from "./assessment-results";
import * as catalogProfiles from "./catalog-profiles";
import * as complianceExplorer from "./compliance-explorer";
import * as measuresMappings from "./measures-mappings";
import * as systems from "./systems";
import type { Locale } from "./locale";

export const en = {
  ...common.en,
  ...assessmentPlans.en,
  ...assessmentResults.en,
  ...catalogProfiles.en,
  ...complianceExplorer.en,
  ...measuresMappings.en,
  ...systems.en,
};
export type TranslationKey = keyof typeof en;
export const de: Record<TranslationKey, string> = {
  ...common.de,
  ...assessmentPlans.de,
  ...assessmentResults.de,
  ...catalogProfiles.de,
  ...complianceExplorer.de,
  ...measuresMappings.de,
  ...systems.de,
};
export type Translate = (key: TranslationKey, values?: Record<string, string | number>) => string;

export function createI18n(locale: Locale) {
  const messages = locale === "de" ? de : en;
  const numberFormat = new Intl.NumberFormat(locale);
  const dateFormat = new Intl.DateTimeFormat(locale, {
    dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
  });
  const t: Translate = (key, values) => {
    let message: string = messages[key] ?? en[key];
    for (const [name, value] of Object.entries(values ?? {})) {
      message = message.split(`{${name}}`).join(String(value));
    }
    return message;
  };
  return {
    locale,
    t,
    number: (value: number) => numberFormat.format(value),
    date: (value: string) => `${dateFormat.format(new Date(value))} UTC`,
    enumLabel: (value: string) => {
      const key = `enums.${value}`;
      return Object.hasOwn(common.en, key) ? t(key as keyof typeof common.en) : value;
    },
    errorMessage: (error: unknown) => {
      if (error instanceof ApiError) {
        const context = t(ERROR_TRANSLATION_KEYS[error.kind]);
        return !error.message || error.message === ERROR_MESSAGES[error.kind]
          ? context
          : `${context} ${t("errors.diagnostic", { detail: error.message })}`;
      }
      return error instanceof Error && error.message
        ? t("errors.diagnostic", { detail: error.message })
        : t("errors.unavailable");
    },
  };
}
