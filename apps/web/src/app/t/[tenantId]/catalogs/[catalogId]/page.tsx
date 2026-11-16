import { ApiProblem } from "@/components/ApiProblem";
import { ControlBrowser } from "@/components/ControlBrowser";
import { getCatalog, getControl, getOutline, getRevision, listRevisions } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { classifyHref, isOscalId, isUuid } from "@/lib/safe";
import type { ControlDetail } from "@/lib/types";
import type { Translate } from "@/lib/i18n";
import { getI18n } from "@/lib/i18n/server";

export default async function CatalogPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string; catalogId: string }>;
  searchParams: Promise<{ revision?: string; control?: string }>;
}) {
  const { t, number, date, enumLabel } = await getI18n();
  const { tenantId, catalogId } = await params;
  const { revision: revisionParam, control: controlParam } = await searchParams;
  const here = `/t/${tenantId}/catalogs/${catalogId}`;
  const loaded = await load(tenantId, catalogId, here, revisionParam, controlParam);
  if (!loaded.ok) return <ApiProblem error={loaded.error} />;
  const { catalog, revisions, selected, revision, root, initialControl } = loaded;
  if (!selected || !revision || !root) {
    return (
      <>
        <Breadcrumbs tenantId={tenantId} name={catalog.name} t={t} />
        <h1>{catalog.name}</h1>
        <div className="empty">{t("catalogPage.noRevisions")}</div>
      </>
    );
  }
  const source = catalog.source_uri ? classifyHref(catalog.source_uri) : null;

  return (
    <>
      <Breadcrumbs tenantId={tenantId} name={catalog.name} t={t} />
      <h1>{catalog.name}</h1>
      <p>
        <span className="badge">
          {t(catalog.origin_type === "imported" ? "catalogPage.imported" : "catalogPage.custom")}
        </span>
      </p>
      {catalog.description ? <p>{catalog.description}</p> : null}

      <section className="panel" aria-labelledby="catalog-source">
        <h2 id="catalog-source">{t("catalogPage.sourceRevision")}</h2>
        <dl className="meta-list">
          <dt>{t("catalogPage.publisher")}</dt>
          <dd>{catalog.source_organization ?? t("common.notRecorded")}</dd>
          <dt>{t("catalogPage.source")}</dt>
          <dd>
            {catalog.source_uri
              ? source?.kind === "external"
                ? (
                    <a href={source.href} target="_blank" rel="noopener noreferrer nofollow">
                      {catalog.source_uri}
                    </a>
                  )
                : catalog.source_uri
              : t("common.notRecorded")}
          </dd>
          <dt>{t("catalogPage.licence")}</dt>
          <dd>{catalog.license_identifier ?? t("common.notRecorded")}</dd>
          <dt>{t("catalogPage.selectedRevision")}</dt>
          <dd>
            {t("common.revisionNumber", { number: number(revision.revision_number) })} · {enumLabel(revision.lifecycle_status)}
            {revision.source_version ? t("common.versionSuffix", { version: revision.source_version }) : ""}
          </dd>
          <dt>{t("common.oscalVersion")}</dt>
          <dd>{revision.oscal_version}</dd>
          <dt>{t("catalogPage.contents")}</dt>
          <dd>
            {t("catalogPage.contentsCount", {
              controls: t(revision.control_count === 1 ? "catalogPage.controlOne" : "catalogPage.controlOther", { count: number(revision.control_count) }),
              groups: t(revision.group_count === 1 ? "catalogPage.groupOne" : "catalogPage.groupOther", { count: number(revision.group_count) }),
            })}
          </dd>
        </dl>

        <form method="get" className="search-form">
          <div className="field">
            <label htmlFor="revision-select">{t("common.revision")}</label>
            <select id="revision-select" name="revision" defaultValue={selected.id}>
              {!revisions.items.some((item) => item.id === selected.id) ? (
                <option value={selected.id}>{t("common.revisionNumber", { number: number(selected.revision_number) })} — {enumLabel(selected.lifecycle_status)}</option>
              ) : null}
              {revisions.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {t("common.revisionNumber", { number: number(item.revision_number) })}
                  {item.source_version ? ` (v${item.source_version})` : ""} — {enumLabel(item.lifecycle_status)}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="secondary">
            {t("catalogPage.viewRevision")}
          </button>
        </form>

        <details>
          <summary>{t("catalogPage.history", { count: number(revisions.total) })}</summary>
          <table>
            <thead>
              <tr>
                <th scope="col">{t("common.revision")}</th>
                <th scope="col">{t("common.status")}</th>
                <th scope="col">{t("common.version")}</th>
                <th scope="col">{t("catalogPage.controls")}</th>
                <th scope="col">{t("catalogPage.imported")}</th>
              </tr>
            </thead>
            <tbody>
              {revisions.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <a href={`${here}?revision=${item.id}`}>{number(item.revision_number)}</a>
                  </td>
                  <td>{enumLabel(item.lifecycle_status)}</td>
                  <td>{item.source_version ?? "—"}</td>
                  <td>{number(item.control_count)}</td>
                  <td><time dateTime={item.created_at}>{date(item.created_at)}</time></td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      <h2>{t("catalogPage.controls")}</h2>
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
    let selected = revisions.items.find((item) => item.id === revisionParam);
    let requestedRevision = null;
    if (!selected && revisionParam && isUuid(revisionParam)) {
      try {
        requestedRevision = await getRevision(tenantId, catalogId, revisionParam, here);
        selected = requestedRevision;
      } catch (error) {
        if (!(error instanceof ApiError && error.kind === "not_found")) throw error;
      }
    }
    selected ??= revisions.items[0];
    if (!selected) {
      return { ok: true as const, catalog, revisions, selected: null, revision: null, root: null, initialControl: null };
    }
    const [revision, root] = await Promise.all([
      requestedRevision ?? getRevision(tenantId, catalogId, selected.id, here),
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


function Breadcrumbs({ tenantId, name, t }: { tenantId: string; name: string; t: Translate }) {
  return (
    <nav className="breadcrumbs" aria-label={t("common.breadcrumb")}>
      <a href={`/t/${tenantId}/catalogs`}>{t("nav.catalogs")}</a> › <span aria-current="page">{name}</span>
    </nav>
  );
}
