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
