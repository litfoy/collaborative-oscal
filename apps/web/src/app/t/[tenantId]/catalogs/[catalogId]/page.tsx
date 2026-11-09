import { ApiProblem } from "@/components/ApiProblem";
import { ControlBrowser } from "@/components/ControlBrowser";
import { getCatalog, getControl, getOutline, getRevision, listRevisions } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { classifyHref, isOscalId } from "@/lib/safe";
import type { ControlDetail } from "@/lib/types";

export default async function CatalogPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string; catalogId: string }>;
  searchParams: Promise<{ revision?: string; control?: string }>;
}) {
  const { tenantId, catalogId } = await params;
  const { revision: revisionParam, control: controlParam } = await searchParams;
  const here = `/t/${tenantId}/catalogs/${catalogId}`;
  const loaded = await load(tenantId, catalogId, here, revisionParam, controlParam);
  if (!loaded.ok) return <ApiProblem error={loaded.error} />;
  const { catalog, revisions, selected, revision, root, initialControl } = loaded;
  if (!selected || !revision || !root) {
    return (
      <>
        <Breadcrumbs tenantId={tenantId} name={catalog.name} />
        <h1>{catalog.name}</h1>
        <div className="empty">This catalog has no revisions yet.</div>
      </>
    );
  }
  const source = catalog.source_uri ? classifyHref(catalog.source_uri) : null;

  return (
    <>
      <Breadcrumbs tenantId={tenantId} name={catalog.name} />
      <h1>{catalog.name}</h1>
      <p>
        <span className="badge">
          {catalog.origin_type === "imported" ? "Imported" : "Internally authored"}
        </span>
      </p>
      {catalog.description ? <p>{catalog.description}</p> : null}

      <section className="panel" aria-labelledby="catalog-source">
        <h2 id="catalog-source">Source and revision</h2>
        <dl className="meta-list">
          <dt>Publisher</dt>
          <dd>{catalog.source_organization ?? "Not recorded"}</dd>
          <dt>Source</dt>
          <dd>
            {catalog.source_uri
              ? source?.kind === "external"
                ? (
                    <a href={source.href} target="_blank" rel="noopener noreferrer nofollow">
                      {catalog.source_uri}
                    </a>
                  )
                : catalog.source_uri
              : "Not recorded"}
          </dd>
          <dt>Licence</dt>
          <dd>{catalog.license_identifier ?? "Not recorded"}</dd>
          <dt>Selected revision</dt>
          <dd>
            Revision {revision.revision_number} · {revision.lifecycle_status}
            {revision.source_version ? ` · version ${revision.source_version}` : ""}
          </dd>
          <dt>OSCAL version</dt>
          <dd>{revision.oscal_version}</dd>
          <dt>Contents</dt>
          <dd>
            {revision.control_count} controls in {revision.group_count} groups
          </dd>
        </dl>

        <form method="get" className="search-form">
          <div className="field">
            <label htmlFor="revision-select">Revision</label>
            <select id="revision-select" name="revision" defaultValue={selected.id}>
              {revisions.items.map((item) => (
                <option key={item.id} value={item.id}>
                  Revision {item.revision_number}
                  {item.source_version ? ` (v${item.source_version})` : ""} — {item.lifecycle_status}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="secondary">
            View revision
          </button>
        </form>

        <details>
          <summary>Revision history ({revisions.total})</summary>
          <table>
            <thead>
              <tr>
                <th scope="col">Revision</th>
                <th scope="col">Status</th>
                <th scope="col">Version</th>
                <th scope="col">Controls</th>
                <th scope="col">Imported</th>
              </tr>
            </thead>
            <tbody>
              {revisions.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <a href={`${here}?revision=${item.id}`}>{item.revision_number}</a>
                  </td>
                  <td>{item.lifecycle_status}</td>
                  <td>{item.source_version ?? "—"}</td>
                  <td>{item.control_count}</td>
                  <td>{new Date(item.created_at).toISOString().slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <h2>Controls</h2>
      <ControlBrowser
        key={selected.id}
        tenantId={tenantId}
        catalogId={catalogId}
        revisionId={selected.id}
        initialRoot={root}
        initialControl={initialControl}
      />
    </>
  );
}

async function load(
  tenantId: string,
  catalogId: string,
  here: string,
  revisionParam: string | undefined,
  controlParam: string | undefined,
) {
  try {
    const [catalog, revisions] = await Promise.all([
      getCatalog(tenantId, catalogId, here),
      listRevisions(tenantId, catalogId, here),
    ]);
    const selected = revisions.items.find((item) => item.id === revisionParam) ?? revisions.items[0];
    if (!selected) {
      return { ok: true as const, catalog, revisions, selected: null, revision: null, root: null, initialControl: null };
    }
    const [revision, root] = await Promise.all([
      getRevision(tenantId, catalogId, selected.id, here),
      getOutline(tenantId, catalogId, selected.id, here),
    ]);

    let initialControl: ControlDetail | null = null;
    if (controlParam && isOscalId(controlParam)) {
      try {
        initialControl = await getControl(tenantId, catalogId, selected.id, controlParam, here);
      } catch (error) {
        if (!(error instanceof ApiError && error.kind === "not_found")) throw error;
      }
    }

    return { ok: true as const, catalog, revisions, selected, revision, root, initialControl };
  } catch (error) {
    return { ok: false as const, error };
  }
}


function Breadcrumbs({ tenantId, name }: { tenantId: string; name: string }) {
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <a href={`/t/${tenantId}/catalogs`}>Catalogs</a> › <span aria-current="page">{name}</span>
    </nav>
  );
}
