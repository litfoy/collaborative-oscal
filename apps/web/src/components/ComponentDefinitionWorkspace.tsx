"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
import type { Catalog, ComponentDefinition, Paged } from "@/lib/types";

export const COMPONENT_TYPES = [
  ["policy", "measures.policy"], ["process-procedure", "measures.processProcedure"], ["service", "measures.service"],
  ["software", "measures.software"], ["hardware", "measures.hardware"], ["physical", "measures.physical"],
  ["plan", "measures.plan"], ["guidance", "measures.guidance"], ["standard", "measures.standard"],
] as const;

export function componentTypeLabel(type: string, t: Translate) {
  const key = COMPONENT_TYPES.find(([value]) => value === type)?.[1];
  return key ? t(key) : type;
}

export function ComponentDefinitionWorkspace({
  tenantId, initialDefinitions, definitionTotal, catalogs, canWrite,
}: {
  tenantId: string;
  initialDefinitions: ComponentDefinition[];
  definitionTotal: number;
  catalogs: Catalog[];
  catalogTotal: number;
  canWrite: boolean;
}) {
  const { t, number, errorMessage } = useI18n();
  const router = useRouter();
  const [definitions, setDefinitions] = useState(initialDefinitions);
  const [total, setTotal] = useState(definitionTotal);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [newType, setNewType] = useState("policy");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const creationDirty = creating && Boolean(title || description || newType !== "policy");
  const matches = definitions.flatMap((document) => document.components.map((component) => ({ document, component })))
    .filter(({ component }) => (!type || component.type === type) &&
      `${component.title}\n${component.description}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));

  useEffect(() => {
    if (!creationDirty && !busy) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (!link || link.getAttribute("href")?.startsWith("#") || link.getAttribute("target") === "_blank" ||
          link.hasAttribute("download") || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      if (busy || !window.confirm(t("measures.newMeasureDraftConfirm"))) event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); };
  }, [creationDirty, busy, t]);

  function cancelCreation() {
    if (busy || (creationDirty && !window.confirm(t("measures.newMeasureDraftConfirm")))) return;
    setCreating(false);
    setTitle("");
    setDescription("");
    setNewType("policy");
  }

  async function create() {
    if (!canWrite || !title.trim() || !description.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await bffWrite<ComponentDefinition>("POST", `tenants/${tenantId}/component-definitions`, {
        title: title.trim(), type: newType, description, requirements: [],
      });
      if (!created.components[0]) {
        setError(t("measures.createdMissingComponent"));
        setDefinitions((current) => [created, ...current]);
        setTotal((current) => current + 1);
        setCreating(false);
        setBusy(false);
        return;
      }
      router.push(`/t/${tenantId}/measures/${created.id}/${created.components[0].id}`);
    } catch (cause) {
      setError(errorMessage(cause) || t("measures.createError"));
      setBusy(false);
    }
  }

  async function loadMore() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const page = await bffGet<Paged<ComponentDefinition>>(`tenants/${tenantId}/component-definitions`, {
        limit: 200, offset: definitions.length,
      });
      setDefinitions((current) => [...current, ...page.items]);
      setTotal(page.total);
    } catch (cause) {
      setError(errorMessage(cause) || t("measures.loadMoreError"));
    } finally {
      setBusy(false);
    }
  }

  if (creating) return <div className="measure-workspace">
    <nav className="breadcrumbs" aria-label={t("measures.breadcrumb")}>
    <button type="button" className="measure-link" disabled={busy} onClick={cancelCreation}>{t("measures.library")}</button> › {t("measures.newMeasure")}
    </nav>
    <h1>{t("measures.newMeasure")}</h1>
    <p className="muted">{t("measures.createReusableGuidance")}</p>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <form className="profile-form" onSubmit={(event) => { event.preventDefault(); void create(); }}>
      <label className="field">{t("measures.title")}
        <input required maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label className="field">{t("measures.componentType")}
        <select value={newType} onChange={(event) => setNewType(event.target.value)}>
          {COMPONENT_TYPES.map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}
        </select>
      </label>
      <label className="field">{t("measures.reusableDescription")}
        <textarea required maxLength={50000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <div className="workspace-actions">
        <button type="submit" disabled={busy || !title.trim() || !description.trim()}>{busy ? t("measures.creating") : t("measures.createMeasure")}</button>
        <button type="button" className="secondary" disabled={busy} onClick={cancelCreation}>{t("measures.cancel")}</button>
      </div>
    </form>
  </div>;

  return <div className="measure-workspace">
    <div className="workspace-actions measure-heading">
      <div><h1>{t("measures.library")}</h1>
        <p className="muted">{t("measures.libraryDescription")}</p>
      </div>
      {canWrite ? <button type="button" onClick={() => { setError(null); setCreating(true); }}>{t("measures.newMeasure")}</button> : null}
    </div>
    {!canWrite ? <p className="muted">{t("measures.permissionCreate")}</p> : null}
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <div className="mapping-control-filters measure-filters">
      <label className="field">{t("measures.search")}
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("measures.searchPlaceholder")} />
      </label>
      <label className="field">{t("measures.componentType")}
        <select value={type} onChange={(event) => setType(event.target.value)}>
          <option value="">{t("measures.allTypes")}</option>
          {COMPONENT_TYPES.map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}
        </select>
      </label>
    </div>
    {matches.length ? <div className="measure-table"><table>
      <thead><tr><th>{t("measures.measure")}</th><th>{t("measures.componentType")}</th><th>{t("measures.requirements")}</th><th>{t("measures.referencedCatalogs")}</th></tr></thead>
      <tbody>{matches.map(({ document, component }) => <tr key={`${document.id}:${component.id}`}>
        <td><a href={`/t/${tenantId}/measures/${document.id}/${component.id}`}>{component.title}</a></td>
        <td>{componentTypeLabel(component.type, t)}</td><td>{number(component.requirements.length)}</td>
        <td>{[...new Set(component.requirements.map((requirement) =>
          catalogs.find((catalog) => catalog.id === requirement.catalog_id)?.name ?? requirement.catalog_id,
        ))].join(", ") || "—"}</td>
      </tr>)}</tbody>
    </table></div> : <p className="empty">{definitions.length === 0 ? t("measures.noMeasures") : t("measures.noFilterMatch")}</p>}
    {definitions.length < total ? <div>
      <p className="muted">{t(total - definitions.length === 1 ? "measures.loadedMeasureNoticeOne" : "measures.loadedMeasureNoticeOther", { count: number(total - definitions.length) })}</p>
      <button type="button" className="secondary" disabled={busy} onClick={() => void loadMore()}>{busy ? t("measures.loading") : t("measures.loadMore")}</button>
    </div> : null}
  </div>;
}
