"use client";

import Link from "next/link";
import type { ApiErrorKind } from "@/lib/errors";
import { useI18n } from "@/lib/i18n/provider";

export function ApiProblemDetails({ kind }: { kind: ApiErrorKind }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="alert">
      <p><strong>{kind === "forbidden" ? t("errors.deniedTitle")
        : kind === "session_expired" ? t("errors.expiredTitle")
        : kind === "not_found" ? t("errors.notFoundTitle")
        : t("errors.genericTitle")}</strong></p>
      <p>{t(`errors.${kind}`)}</p>
      <p>{kind === "session_expired"
        ? <a className="button" href="/auth/login">{t("auth.signInAgain")}</a>
        : <Link href="/">{t("nav.backWorkspaces")}</Link>}</p>
    </div>
  );
}
