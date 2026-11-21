// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import type { Tenant } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

import { LanguageSelector } from "./LanguageSelector";

export function AppShell({
  userName,
  tenants,
  currentTenantId,
  demoMode = false,
  children,
}: {
  userName: string;
  tenants: Tenant[];
  currentTenantId?: string;
  demoMode?: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const current = tenants.find((tenant) => tenant.id === currentTenantId);
  return (
    <>
      <a className="skip-link" href="#main">
        {t("nav.skip")}
      </a>
      <header className="shell-header">
        <nav aria-label={t("nav.primary")}>
          <Link className="brand" href="/">
            Collaborative OSCAL
          </Link>
          {current ? (
            <>
              <a href={`/t/${current.id}`}>{t("nav.overview")}</a>
              <a href={`/t/${current.id}/catalogs`}>{t("nav.catalogs")}</a>
              <a href={`/t/${current.id}/measures`}>{t("nav.measures")}</a>
              <a href={`/t/${current.id}/mappings`}>{t("nav.mappings")}</a>
              <a href={`/t/${current.id}/profiles`}>{t("nav.profiles")}</a>
              <a href={`/t/${current.id}/systems`}>{t("nav.systems")}</a>
              <a href={`/t/${current.id}/compliance-explorer`}>{t("nav.complianceExplorer")}</a>
              <a href={`/t/${current.id}/assessment-plans`}>{t("nav.assessmentPlans")}</a>
              <a href={`/t/${current.id}/assessment-results`}>{t("nav.assessmentResults")}</a>
              <span className="muted">{t("nav.workspace")} {current.name}</span>
              {tenants.length > 1 ? <Link href="/">{t("nav.switchWorkspace")}</Link> : null}
            </>
          ) : null}
        </nav>
        <div className="shell-user">
          <LanguageSelector />
          {demoMode ? <strong>{t("auth.demoMode")}</strong> : null}
          <span>{userName}</span>
          {!demoMode ? (
          <form action="/auth/logout" method="post">
            <button type="submit" className="secondary">
              {t("auth.signOut")}
            </button>
          </form>
          ) : null}
        </div>
      </header>
      <main id="main" className="page">
        {children}
      </main>
    </>
  );
}
