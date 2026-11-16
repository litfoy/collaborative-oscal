"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n/provider";

export default function NotFound() {
  const { t } = useI18n();
  return (
    <main id="main" className="page page-narrow">
      <div className="panel">
        <h1>{t("errors.pageNotFound")}</h1>
        <Link href="/">{t("nav.backWorkspaces")}</Link>
      </div>
    </main>
  );
}
