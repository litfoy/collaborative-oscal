import { ApiProblem } from "@/components/ApiProblem";
import { listCatalogs, listMappingCollections, listTenants } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";

export default async function MappingCollectionsPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { t, number } = await getI18n();
  const { tenantId } = await params;
  const here = `/t/${tenantId}/mappings`;
  const result = await loadMappingList(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  const { collections, catalogs, canWrite } = result;
  const catalogNames = new Map(catalogs.items.map((catalog) => [catalog.id, catalog.name]));
  return <>
      <h1>{t("nav.mappings")}</h1>
      <p className="muted">{t("mappingPage.intro")}</p>
      {canWrite ? <p><a className="button" href={`${here}/new`}>{t("mappingPage.create")}</a></p> : null}
      {collections.items.length === 0 ? <div className="empty">
        <p>{t("mappingPage.empty")}</p>
        {canWrite ? <p>{t("mappingPage.createHint")}</p> : null}
      </div> : <ul className="card-grid" aria-label={t("mappingPage.collections")}>
        {collections.items.map((collection) => {
          const entryCount = collection.mappings.reduce((total, mapping) => total + mapping.entries.length, 0);
          return <li className="card" key={collection.id}>
            <h2><a href={`${here}/${collection.id}`}>{collection.title}</a></h2>
            {collection.description ? <p>{collection.description}</p> : null}
            <dl className="meta-list">
              <dt>{t("mappingPage.pairs")}</dt><dd>{number(collection.mappings.length)}</dd>
              <dt>{t("mappingPage.entries")}</dt><dd>{number(entryCount)}</dd>
              <dt>{t("common.oscalVersion")}</dt><dd>{collection.oscal_version}</dd>
            </dl>
            <ul>{collection.mappings.map((mapping) => <li key={mapping.id}>
              {catalogNames.get(mapping.source_catalog_id) ?? mapping.source_catalog_id}{t("mappingPage.revision", { revision: mapping.source_revision_id })}
              {" → "}
              {catalogNames.get(mapping.target_catalog_id) ?? mapping.target_catalog_id}{t("mappingPage.revision", { revision: mapping.target_revision_id })}
            </li>)}</ul>
            <a className="button secondary" href={`/bff/tenants/${tenantId}/mapping-collections/${collection.id}/export`}>{t("common.exportJson")}</a>
          </li>;
        })}
      </ul>}
      {collections.total > collections.items.length ? <p role="status" className="muted">{t("mappingPage.showing", { count: number(collections.items.length), total: number(collections.total) })}</p> : null}
      {catalogs.total > catalogs.items.length ? <p className="muted">{t("mappingPage.catalogLimit", { count: number(catalogs.items.length) })}</p> : null}
  </>;
}

async function loadMappingList(tenantId: string, returnTo: string) {
  try {
    const [collections, catalogs, tenants] = await Promise.all([
      listMappingCollections(tenantId, returnTo),
      listCatalogs(tenantId, { limit: 200, offset: 0 }, returnTo),
      listTenants(returnTo),
    ]);
    return {
      ok: true as const,
      collections,
      catalogs,
      canWrite: tenants.items.some((tenant) =>
        tenant.id === tenantId && tenant.permissions.includes("catalog:write"),
      ),
    };
  } catch (error) {
    return { ok: false as const, error };
  }
}
