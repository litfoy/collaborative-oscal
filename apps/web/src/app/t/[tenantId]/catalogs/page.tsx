import { ApiProblem } from "@/components/ApiProblem";
import { CatalogImport } from "@/components/CatalogImport";
import { listCatalogs, listTenants } from "@/lib/api";
import type { Catalog } from "@/lib/types";

const PAGE_SIZE = 12;

function CatalogCard({ catalog, tenantId }: { catalog: Catalog; tenantId: string }) {
  const latest = catalog.latest_revision;
  return (
    <li className="card">
      <h2>
        <a href={`/t/${tenantId}/catalogs/${catalog.id}`}>{catalog.name}</a>
      </h2>
      <p>
        <span className="badge">
          {catalog.origin_type === "imported" ? "Imported" : "Internally authored"}
        </span>
      </p>
      {catalog.description ? <p>{catalog.description}</p> : null}
      <dl className="meta-list">
        <dt>Publisher</dt>
        <dd>{catalog.source_organization ?? "Not recorded"}</dd>
        <dt>Revisions</dt>
        <dd>{catalog.revision_count}</dd>
        <dt>Latest</dt>
        <dd>
          {latest
            ? `Revision ${latest.revision_number}${latest.source_version ? ` (v${latest.source_version})` : ""} · ${latest.lifecycle_status}`
            : "None"}
        </dd>
        <dt>OSCAL version</dt>
        <dd>{latest?.oscal_version ?? "—"}</dd>
        <dt>Controls</dt>
        <dd>{latest?.control_count ?? "—"}</dd>
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
      <h1>Catalogs</h1>
      <p className="muted">
        Control catalogs available in this workspace. Catalog sources may carry their own licence
        terms.
      </p>
      {canImport ? <CatalogImport tenantId={tenantId} /> : null}
      <form role="search" method="get" className="search-form">
        <div className="field">
          <label htmlFor="catalog-q">Search catalogs</label>
          <input id="catalog-q" name="q" type="search" defaultValue={term} maxLength={200} />
        </div>
        <button type="submit">Search</button>
      </form>

      {result.items.length === 0 ? (
        <div className="empty">
          {term ? (
            <p>No catalogs match “{term}”.</p>
          ) : (
            <>
              <p>This workspace has no catalogs yet.</p>
              <p>An administrator can import an OSCAL catalog to get started.</p>
            </>
          )}
        </div>
      ) : (
        <ul className="card-grid" aria-label="Catalogs">
          {result.items.map((catalog) => (
            <CatalogCard key={catalog.id} catalog={catalog} tenantId={tenantId} />
          ))}
        </ul>
      )}

      {pages > 1 ? (
        <nav className="pagination" aria-label="Catalog pages">
          {page > 1 ? <a href={link(page - 1)}>Previous</a> : null}
          <span>
            Page {page} of {pages}
          </span>
          {page < pages ? <a href={link(page + 1)}>Next</a> : null}
        </nav>
      ) : null}
    </>
  );
}
