import { ApiProblem } from "@/components/ApiProblem";
import { listCatalogs, listMappingCollections, listTenants } from "@/lib/api";

export default async function MappingCollectionsPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const here = `/t/${tenantId}/mappings`;
  const result = await loadMappingList(tenantId, here);
  if (!result.ok) return <ApiProblem error={result.error} />;
  const { collections, catalogs, canWrite } = result;
  const catalogNames = new Map(catalogs.items.map((catalog) => [catalog.id, catalog.name]));
  return <>
      <h1>Control mappings</h1>
      <p className="muted">Describe explicit relationships between controls in pinned catalog revisions. Mapping relationships do not modify catalogs, profiles, or implementation status.</p>
      {canWrite ? <p><a className="button" href={`${here}/new`}>Create mapping collection</a></p> : null}
      {collections.items.length === 0 ? <div className="empty">
        <p>No Control Mapping collections exist in this workspace.</p>
        {canWrite ? <p>Create a collection to begin defining explicit relationships between catalog controls.</p> : null}
      </div> : <ul className="card-grid" aria-label="Control Mapping collections">
        {collections.items.map((collection) => {
          const entryCount = collection.mappings.reduce((total, mapping) => total + mapping.entries.length, 0);
          return <li className="card" key={collection.id}>
            <h2><a href={`${here}/${collection.id}`}>{collection.title}</a></h2>
            {collection.description ? <p>{collection.description}</p> : null}
            <dl className="meta-list">
              <dt>Catalog pairs</dt><dd>{collection.mappings.length}</dd>
              <dt>Mapping entries</dt><dd>{entryCount}</dd>
              <dt>OSCAL version</dt><dd>{collection.oscal_version}</dd>
            </dl>
            <ul>{collection.mappings.map((mapping) => <li key={mapping.id}>
              {catalogNames.get(mapping.source_catalog_id) ?? mapping.source_catalog_id} · revision {mapping.source_revision_id}
              {" → "}
              {catalogNames.get(mapping.target_catalog_id) ?? mapping.target_catalog_id} · revision {mapping.target_revision_id}
            </li>)}</ul>
            <a className="button secondary" href={`/bff/tenants/${tenantId}/mapping-collections/${collection.id}/export`}>Export OSCAL JSON</a>
          </li>;
        })}
      </ul>}
      {collections.total > collections.items.length ? <p role="status" className="muted">Showing {collections.items.length} of {collections.total} collections.</p> : null}
      {catalogs.total > catalogs.items.length ? <p className="muted">The catalog picker currently shows the first {catalogs.items.length} accessible catalogs.</p> : null}
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
