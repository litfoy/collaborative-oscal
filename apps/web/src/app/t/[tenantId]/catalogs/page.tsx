// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { ApiProblem } from "@/components/ApiProblem";
import { CatalogImport } from "@/components/CatalogImport";
import { listCatalogs, listTenants } from "@/lib/api";
import type { Catalog } from "@/lib/types";
import { getI18n } from "@/lib/i18n/server";
import type { createI18n } from "@/lib/i18n";

const PAGE_SIZE = 12;

function CatalogCard({ catalog, tenantId, i18n }: { catalog: Catalog; tenantId: string; i18n: ReturnType<typeof createI18n> }) {
  const { t, number, enumLabel } = i18n;
  const latest = catalog.latest_revision;
  return (
    <li className="card">
      <h2>
        <a href={`/t/${tenantId}/catalogs/${catalog.id}`}>{catalog.name}</a>
      </h2>
      <p>
        <span className="badge">
          {t(catalog.origin_type === "imported" ? "catalogPage.imported" : "catalogPage.custom")}
        </span>
      </p>
      {catalog.description ? <p>{catalog.description}</p> : null}
      <dl className="meta-list">
        <dt>{t("catalogPage.publisher")}</dt>
        <dd>{catalog.source_organization ?? t("common.notRecorded")}</dd>
        <dt>{t("catalogPage.revisions")}</dt>
        <dd>{number(catalog.revision_count)}</dd>
        <dt>{t("catalogPage.latest")}</dt>
        <dd>
          {latest
            ? `${t("common.revisionNumber", { number: number(latest.revision_number) })}${latest.source_version ? ` (v${latest.source_version})` : ""} · ${enumLabel(latest.lifecycle_status)}`
            : t("common.none")}
        </dd>
        <dt>{t("common.oscalVersion")}</dt>
        <dd>{latest?.oscal_version ?? "—"}</dd>
        <dt>{t("catalogPage.controls")}</dt>
        <dd>{latest ? number(latest.control_count) : "—"}</dd>
      </dl>
    </li>
  );
}

export default async function CatalogsPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const i18n = await getI18n();
  const { t, number } = i18n;
  const { tenantId } = await params;
  const { q = "", page: pageParam } = await searchParams;
  const page = Math.max(1, Number.parseInt(pageParam ?? "1", 10) || 1);
  const term = q.trim().slice(0, 200);
  const here = `/t/${tenantId}/catalogs`;

  let result;
  let canImport;
  try {
    const [catalogs, tenants] = await Promise.all([
      listCatalogs(tenantId, { q: term, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }, here),
      listTenants(here),
    ]);
    result = catalogs;
    canImport = tenants.items.some((tenant) => tenant.id === tenantId && tenant.permissions.includes("catalog:import"));
  } catch (error) {
    return <ApiProblem error={error} />;
  }

  const pages = Math.max(1, Math.ceil(result.total / PAGE_SIZE));
  const link = (target: number) =>
    `${here}?${new URLSearchParams({ ...(term ? { q: term } : {}), page: String(target) })}`;

  return (
    <>
      <h1>{t("nav.catalogs")}</h1>
      <p className="muted">
        {t("catalogPage.intro")}
      </p>
      {canImport ? <CatalogImport tenantId={tenantId} /> : null}
      <form role="search" method="get" className="search-form">
        <div className="field">
          <label htmlFor="catalog-q">{t("catalogPage.search")}</label>
          <input id="catalog-q" name="q" type="search" defaultValue={term} maxLength={200} />
        </div>
        <button type="submit">{t("common.search")}</button>
      </form>

      {result.items.length === 0 ? (
        <div className="empty">
          {term ? (
            <p>{t("catalogPage.noMatch", { term })}</p>
          ) : (
            <>
              <p>{t("catalogPage.empty")}</p>
              <p>{t("catalogPage.importHint")}</p>
            </>
          )}
        </div>
      ) : (
        <ul className="card-grid" aria-label={t("nav.catalogs")}>
          {result.items.map((catalog) => (
            <CatalogCard key={catalog.id} catalog={catalog} tenantId={tenantId} i18n={i18n} />
          ))}
        </ul>
      )}

      {pages > 1 ? (
        <nav className="pagination" aria-label={t("catalogPage.pages")}>
          {page > 1 ? <a href={link(page - 1)}>{t("common.previous")}</a> : null}
          <span>
            {t("common.page", { page: number(page), pages: number(pages) })}
          </span>
          {page < pages ? <a href={link(page + 1)}>{t("common.next")}</a> : null}
        </nav>
      ) : null}
    </>
  );
}
