"use client";

import { useI18n } from "@/lib/i18n/provider";

export default function ErrorBoundary({ reset }: { error: Error; reset: () => void }) {
  const { t } = useI18n();
  return (
    <main id="main" className="page page-narrow">
      <div role="alert" className="alert">
        <p>
          <strong>{t("errors.boundaryTitle")}</strong>
        </p>
        <p>{t("errors.pageFailed")}</p>
        <button type="button" onClick={reset}>
          {t("errors.retry")}
        </button>
      </div>
    </main>
  );
}
