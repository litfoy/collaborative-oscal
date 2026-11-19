// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import "server-only";

import { cookies } from "next/headers";

import { createI18n } from ".";
import { LOCALE_COOKIE, resolveLocale } from "./locale";

export async function getI18n() {
  return createI18n(resolveLocale((await cookies()).get(LOCALE_COOKIE)?.value));
}
