// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useI18n } from "@/lib/i18n/provider";

export default function Loading() {
  const { t } = useI18n();
  return (
    <p role="status" className="page muted">
      {t("common.loading")}
    </p>
  );
}
