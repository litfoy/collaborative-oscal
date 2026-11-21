// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { listSystems, listTenants } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";

export default async function WorkspaceOverviewPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { t } = await getI18n();
  const { tenantId } = await params;
  const here = `/t/${tenantId}`;
  const result = await loadWorkspaceOverview(tenantId, here);
  const workspaceName = result.tenantName ?? tenantId;

  return (
    <div className="workspace-overview">
      <header>
        <h1>{t("workspaceOverview.title", { workspace: workspaceName })}</h1>
        <p className="muted">{t("workspaceOverview.intro")}</p>
      </header>

      <nav aria-label={t("workspaceOverview.primaryNav")}>
        <ul className="card-grid" aria-label={t("workspaceOverview.primaryNav")}>
          <li className="card">
            <h2>{t("workspaceOverview.systems.title")}</h2>
            <p className="muted">{t("workspaceOverview.systems.description")}</p>
            <p>
              <a href={`/t/${tenantId}/systems`}>{t("workspaceOverview.systems.link")}</a>
            </p>
          </li>
          <li className="card">
            <h2>{t("workspaceOverview.requirements.title")}</h2>
            <p className="muted">{t("workspaceOverview.requirements.description")}</p>
            <p>
              <a href={`/t/${tenantId}/compliance-explorer`}>
                {t("workspaceOverview.requirements.link")}
              </a>
            </p>
          </li>
          <li className="card">
            <h2>{t("workspaceOverview.measures.title")}</h2>
            <p className="muted">{t("workspaceOverview.measures.description")}</p>
            <p>
              <a href={`/t/${tenantId}/compliance-explorer`}>
                {t("workspaceOverview.measures.systemMeasuresLink")}
              </a>
            </p>
            <p>
              <a href={`/t/${tenantId}/measures`}>
                {t("workspaceOverview.measures.libraryLink")}
              </a>
            </p>
          </li>
          <li className="card">
            <h2>{t("workspaceOverview.assessments.title")}</h2>
            <p className="muted">{t("workspaceOverview.assessments.description")}</p>
            <p>
              <a href={`/t/${tenantId}/assessment-plans`}>
                {t("workspaceOverview.assessments.plansLink")}
              </a>
            </p>
            <p>
              <a href={`/t/${tenantId}/assessment-results`}>
                {t("workspaceOverview.assessments.resultsLink")}
              </a>
            </p>
          </li>
        </ul>
      </nav>

      <section className="panel" aria-labelledby="workspace-libraries-heading">
        <h2 id="workspace-libraries-heading">{t("workspaceOverview.libraries.title")}</h2>
        <p className="muted">{t("workspaceOverview.libraries.description")}</p>
        <ul className="workspace-overview-links">
          <li><a href={`/t/${tenantId}/catalogs`}>{t("nav.catalogs")}</a></li>
          <li><a href={`/t/${tenantId}/profiles`}>{t("nav.profiles")}</a></li>
          <li><a href={`/t/${tenantId}/measures`}>{t("workspaceOverview.libraries.componentDefinitions")}</a></li>
          <li><a href={`/t/${tenantId}/mappings`}>{t("nav.mappings")}</a></li>
        </ul>
      </section>

      <section aria-labelledby="workspace-systems-heading">
        <h2 id="workspace-systems-heading">{t("workspaceOverview.systemSummary.title")}</h2>
        {!result.ok ? (
          <ApiProblem error={result.error} />
        ) : result.systems.length === 0 ? (
          <div className="empty">{t("workspaceOverview.systemSummary.empty")}</div>
        ) : (
          <>
            <ul className="profile-list" aria-label={t("workspaceOverview.systemSummary.list")}>
              {result.systems.slice(0, 6).map((system) => (
                <li className="panel" key={system.id}>
                  <h3>{system.name}</h3>
                  <p className="muted">{system.description ?? t("workspaceOverview.systemSummary.noDescription")}</p>
                  <a href={`/t/${tenantId}/systems/${system.id}`}>
                    {t("workspaceOverview.systemSummary.openSystem")}
                  </a>
                </li>
              ))}
            </ul>
            <p>
              <a href={`/t/${tenantId}/systems`}>
                {t("workspaceOverview.systemSummary.allSystems", { count: result.systems.length })}
              </a>
            </p>
          </>
        )}
      </section>
    </div>
  );
}

async function loadWorkspaceOverview(tenantId: string, returnTo: string) {
  let tenantName: string | null = null;
  try {
    const tenants = await listTenants(returnTo);
    tenantName = tenants.items.find((tenant) => tenant.id === tenantId)?.name ?? null;
  } catch {
    tenantName = null;
  }

  try {
    const systems = await listSystems(tenantId, returnTo);
    return {
      ok: true as const,
      tenantName,
      systems,
    };
  } catch (error) {
    return {
      ok: false as const,
      tenantName,
      error,
    };
  }
}

