// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

export const LOCALES = ["en", "de"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "co_locale";
export const LOCALE_MAX_AGE = 60 * 60 * 24 * 365;

export function resolveLocale(value: unknown): Locale {
  return value === "de" ? "de" : DEFAULT_LOCALE;
}
