"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import type { Catalog, ComponentDefinition, Paged } from "@/lib/types";

export const COMPONENT_TYPES = [
  ["policy", "Policy"], ["process-procedure", "Process or procedure"], ["service", "Service"],
  ["software", "Software"], ["hardware", "Hardware"], ["physical", "Physical"],
  ["plan", "Plan"], ["guidance", "Guidance"], ["standard", "Standard"],
] as const;

export function componentTypeLabel(type: string) {
  return COMPONENT_TYPES.find(([value]) => value === type)?.[1] ?? type;
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
      if (busy || !window.confirm("Discard the new measure draft?")) event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); };
  }, [creationDirty, busy]);

  function cancelCreation() {
    if (busy || (creationDirty && !window.confirm("Discard the new measure draft?"))) return;
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
        setError("The measure was created, but the response did not contain a component. Return to the library to find it.");
        setDefinitions((current) => [created, ...current]);
        setTotal((current) => current + 1);
        setCreating(false);
        setBusy(false);
        return;
      }
      router.push(`/t/${tenantId}/measures/${created.id}/${created.components[0].id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create the measure.");
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
      setError(cause instanceof Error ? cause.message : "Unable to load more measures.");
    } finally {
      setBusy(false);
    }
  }

  if (creating) return <div className="measure-workspace">
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <button type="button" className="measure-link" disabled={busy} onClick={cancelCreation}>Our Measures &amp; Controls</button> › New measure
    </nav>
    <h1>New measure</h1>
    <p className="muted">Create reusable guidance; associations can be added after creation.</p>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <form className="profile-form" onSubmit={(event) => { event.preventDefault(); void create(); }}>
      <label className="field">Measure title
        <input required maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label className="field">Component type
        <select value={newType} onChange={(event) => setNewType(event.target.value)}>
          {COMPONENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="field">Reusable description
        <textarea required maxLength={50000} rows={5} value={description} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <div className="workspace-actions">
        <button type="submit" disabled={busy || !title.trim() || !description.trim()}>{busy ? "Creating…" : "Create measure"}</button>
        <button type="button" className="secondary" disabled={busy} onClick={cancelCreation}>Cancel</button>
      </div>
    </form>
  </div>;

  return <div className="measure-workspace">
    <div className="workspace-actions measure-heading">
      <div><h1>Our Measures &amp; Controls</h1>
        <p className="muted">Reusable guidance associated with pinned requirements, not evidence of deployment or assessment.</p>
      </div>
      {canWrite ? <button type="button" onClick={() => { setError(null); setCreating(true); }}>New measure</button> : null}
    </div>
    {!canWrite ? <p className="muted">You need catalog:write permission to create or edit measures.</p> : null}
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <div className="mapping-control-filters measure-filters">
      <label className="field">Search measures
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title or description" />
      </label>
      <label className="field">Component type
        <select value={type} onChange={(event) => setType(event.target.value)}>
          <option value="">All types</option>
          {COMPONENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
    </div>
    {matches.length ? <div className="measure-table"><table>
      <thead><tr><th>Measure</th><th>Component type</th><th>Requirements</th><th>Referenced catalogs</th></tr></thead>
      <tbody>{matches.map(({ document, component }) => <tr key={`${document.id}:${component.id}`}>
        <td><a href={`/t/${tenantId}/measures/${document.id}/${component.id}`}>{component.title}</a></td>
        <td>{componentTypeLabel(component.type)}</td><td>{component.requirements.length}</td>
        <td>{[...new Set(component.requirements.map((requirement) =>
          catalogs.find((catalog) => catalog.id === requirement.catalog_id)?.name ?? requirement.catalog_id,
        ))].join(", ") || "—"}</td>
      </tr>)}</tbody>
    </table></div> : <p className="empty">{definitions.length === 0 ? "No reusable measures yet." : "No measures match these filters."}</p>}
    {definitions.length < total ? <div>
      <p className="muted">Search and filters apply to loaded measures. {total - definitions.length} more documents are available.</p>
      <button type="button" className="secondary" disabled={busy} onClick={() => void loadMore()}>{busy ? "Loading…" : "Load more measures"}</button>
    </div> : null}
  </div>;
}
