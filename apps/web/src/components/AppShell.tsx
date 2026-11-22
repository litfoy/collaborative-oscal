// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { Tenant } from "@/lib/types";
import { useI18n } from "@/lib/i18n/provider";

import { LanguageSelector } from "./LanguageSelector";

type NavKey =
  | "overview"
  | "systems"
  | "requirementsMeasures"
  | "assessmentPlans"
  | "assessmentResults"
  | "catalogs"
  | "profiles"
  | "componentDefinitions"
  | "mappings";

type ActiveNav = {
  key: NavKey;
  current: "page" | "location";
};

function resolveActiveNav(pathname: string | null, tenantId: string): ActiveNav | null {
  if (!pathname) return null;
  const base = `/t/${tenantId}`;
  if (pathname === base || pathname === `${base}/`) {
    return { key: "overview", current: "page" };
  }
  if (!pathname.startsWith(`${base}/`)) {
    return null;
  }
  const [firstSegment, ...rest] = pathname.slice(base.length + 1).split("/");
  const current = rest.length === 0 || (rest.length === 1 && rest[0] === "")
    ? "page"
    : "location";
  switch (firstSegment) {
    case "systems":
      return { key: "systems", current };
    case "compliance-explorer":
      return { key: "requirementsMeasures", current };
    case "assessment-plans":
      return { key: "assessmentPlans", current };
    case "assessment-results":
      return { key: "assessmentResults", current };
    case "catalogs":
      return { key: "catalogs", current };
    case "profiles":
      return { key: "profiles", current };
    case "measures":
      return { key: "componentDefinitions", current };
    case "mappings":
      return { key: "mappings", current };
    default:
      return null;
  }
}

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
  const pathname = usePathname();
  const [mobileNavExpanded, setMobileNavExpanded] = useState(false);
  const current = tenants.find((tenant) => tenant.id === currentTenantId);
  const activeNav = useMemo(
    () => (current ? resolveActiveNav(pathname, current.id) : null),
    [pathname, current],
  );
  const navId = current ? `workspace-nav-${current.id}` : undefined;

  const navLink = (key: NavKey, href: string, label: string) => (
    <Link
      href={href}
      className="shell-nav-link"
      aria-current={activeNav?.key === key ? activeNav.current : undefined}
      onClick={() => setMobileNavExpanded(false)}
    >
      {label}
    </Link>
  );

  return (
    <>
      <a className="skip-link" href="#main">
        {t("nav.skip")}
      </a>
      <header className="shell-header">
        <div className="shell-header-main">
          <Link className="brand" href="/">
            Collaborative OSCAL
          </Link>
          {current ? (
            <>
              <span className="muted shell-workspace-name">
                {t("nav.workspace")} {current.name}
              </span>
              {tenants.length > 1 ? <Link href="/">{t("nav.switchWorkspace")}</Link> : null}
            </>
          ) : null}
        </div>
        <div className="shell-user">
          {current ? (
            <button
              type="button"
              className="secondary shell-nav-toggle"
              aria-expanded={mobileNavExpanded}
              aria-controls={navId}
              onClick={() => setMobileNavExpanded((expanded) => !expanded)}
            >
              {mobileNavExpanded ? t("nav.closeNavigation") : t("nav.openNavigation")}
            </button>
          ) : null}
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

      {current ? (
        <div className="shell-layout">
          <aside className="shell-sidebar" data-open={mobileNavExpanded ? "true" : "false"}>
            <nav id={navId} className="shell-nav" aria-label={t("nav.primary")}>
              <section aria-labelledby="workspace-nav-section-workspace">
                <h2 id="workspace-nav-section-workspace" className="shell-nav-section-title">
                  {t("nav.sectionWorkspace")}
                </h2>
                {navLink("overview", `/t/${current.id}`, t("nav.overview"))}
              </section>

              <section aria-labelledby="workspace-nav-section-explorer">
                <h2 id="workspace-nav-section-explorer" className="shell-nav-section-title">
                  {t("nav.sectionExplorer")}
                </h2>
                {navLink("systems", `/t/${current.id}/systems`, t("nav.systems"))}
                {navLink(
                  "requirementsMeasures",
                  `/t/${current.id}/compliance-explorer`,
                  t("nav.requirementsMeasures"),
                )}
                <div className="shell-nav-subgroup" aria-label={t("nav.assessments")}>
                  <p className="shell-nav-group-title">{t("nav.assessments")}</p>
                  {navLink("assessmentPlans", `/t/${current.id}/assessment-plans`, t("nav.assessmentPlans"))}
                  {navLink("assessmentResults", `/t/${current.id}/assessment-results`, t("nav.assessmentResults"))}
                </div>
              </section>

              <section aria-labelledby="workspace-nav-section-libraries">
                <h2 id="workspace-nav-section-libraries" className="shell-nav-section-title">
                  {t("nav.sectionLibrariesModeling")}
                </h2>
                {navLink("catalogs", `/t/${current.id}/catalogs`, t("nav.catalogs"))}
                {navLink("profiles", `/t/${current.id}/profiles`, t("nav.profiles"))}
                {navLink("componentDefinitions", `/t/${current.id}/measures`, t("nav.componentDefinitions"))}
                {navLink("mappings", `/t/${current.id}/mappings`, t("nav.mappings"))}
              </section>
            </nav>
          </aside>

          <main id="main" className="page shell-main">
            {children}
          </main>
        </div>
      ) : (
        <main id="main" className="page">
          {children}
        </main>
      )}
    </>
  );
}
