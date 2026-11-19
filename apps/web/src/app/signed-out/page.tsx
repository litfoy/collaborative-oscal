// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { LanguageSelector } from "@/components/LanguageSelector";
import { getI18n } from "@/lib/i18n/server";

export default async function SignedOutPage() {
  const { t } = await getI18n();
  return (
    <>
    <header className="shell-header"><span className="brand">Collaborative OSCAL</span><LanguageSelector /></header>
    <main id="main" className="page page-narrow">
      <div className="panel">
        <h1>{t("auth.signedOut")}</h1>
        <p className="muted">{t("auth.sessionEnded")}</p>
        <a className="button" href="/auth/login">
          {t("auth.signInAgain")}
        </a>
      </div>
    </main>
    </>
  );
}
