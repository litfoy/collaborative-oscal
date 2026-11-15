"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MappingControlPicker } from "@/components/MappingControlPicker";
import { bffGet } from "@/lib/bff-client";
import type { Catalog, ComponentRequirementInput, Paged, RevisionSummary } from "@/lib/types";

export function MeasureRequirementPicker({
  tenantId, catalogs: initialCatalogs, catalogTotal, existing, onConfirm, onCancel, onPendingChange,
}: {
  tenantId: string;
  catalogs: Catalog[];
  catalogTotal: number;
  existing: ComponentRequirementInput[];
  onConfirm: (requirements: ComponentRequirementInput[]) => void;
  onCancel: () => void;
  onPendingChange: (pending: boolean) => void;
}) {
  const [catalogs, setCatalogs] = useState(initialCatalogs);
  const [catalogId, setCatalogId] = useState(initialCatalogs.find((catalog) => catalog.latest_revision)?.id ?? "");
  const [revisionId, setRevisionId] = useState("");
  const [revisionOffset, setRevisionOffset] = useState(0);
  const [revisionPage, setRevisionPage] = useState<Paged<RevisionSummary> | null>(null);
  const [revisionNumbers, setRevisionNumbers] = useState<Record<string, number>>({});
  const [pending, setPending] = useState<ComponentRequirementInput[]>([]);
  const [titles, setTitles] = useState<Record<string, Record<string, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const catalog = catalogs.find((item) => item.id === catalogId);
  const key = `${catalogId}:${revisionId}`;
  const selected = pending.filter((item) => item.catalog_id === catalogId && item.revision_id === revisionId);
  const unavailable = existing.filter((item) => item.catalog_id === catalogId && item.revision_id === revisionId);
  const reportTitles = useCallback((values: Record<string, string>) => {
    setTitles((current) => ({ ...current, [key]: values }));
  }, [key]);

  useEffect(() => { heading.current?.focus(); }, []);

  useEffect(() => {
    if (!catalogId) return;
    const controller = new AbortController();
    bffGet<Paged<RevisionSummary>>(`tenants/${tenantId}/catalogs/${catalogId}/revisions`,
      { limit: 200, offset: revisionOffset }, controller.signal)
      .then((result) => {
        setRevisionPage(result);
        setRevisionNumbers((current) => ({
          ...current, ...Object.fromEntries(result.items.map((item) => [item.id, item.revision_number])),
        }));
        setRevisionId((current) => result.items.some((item) => item.id === current) ? current : "");
        setError(null);
      }).catch((cause: unknown) => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load revisions.");
      });
    return () => controller.abort();
  }, [tenantId, catalogId, revisionOffset]);

  function updatePending(next: ComponentRequirementInput[]) {
    setPending(next);
    onPendingChange(next.length > 0);
  }

  async function loadMoreCatalogs() {
    setLoading(true);
    setError(null);
    try {
      const result = await bffGet<Paged<Catalog>>(`tenants/${tenantId}/catalogs`, { limit: 200, offset: catalogs.length });
      setCatalogs((current) => [...current, ...result.items]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load catalogs.");
    } finally {
      setLoading(false);
    }
  }

  return <section className="panel measure-picker">
    <div className="workspace-actions measure-heading">
      <div><h2 ref={heading} tabIndex={-1}>Add requirements</h2><p className="muted">Select requirements explicitly. Existing associations cannot be selected again.</p></div>
      <button type="button" className="secondary" onClick={onCancel}>Cancel</button>
      <button type="button" disabled={!pending.length} onClick={() => onConfirm(pending)}>Add selected ({pending.length})</button>
    </div>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <div className="mapping-control-filters">
      <label className="field">Catalog
        <select value={catalogId} onChange={(event) => {
          setCatalogId(event.target.value); setRevisionId(""); setRevisionPage(null); setRevisionOffset(0);
        }}>
          <option value="">Select a catalog</option>
          {catalogs.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <label className="field">Catalog revision
        <select value={revisionId} onChange={(event) => setRevisionId(event.target.value)}>
          <option value="">Select a revision</option>
          {revisionPage?.items.map((item) => <option key={item.id} value={item.id}>
            Revision {item.revision_number} · {item.lifecycle_status}
          </option>)}
        </select>
      </label>
    </div>
    {catalogs.length < catalogTotal ? <button type="button" className="secondary" disabled={loading} onClick={() => void loadMoreCatalogs()}>
      {loading ? "Loading…" : "Load more catalogs"}
    </button> : null}
    {revisionPage && revisionPage.total > 200 ? <div className="workspace-actions">
      <button type="button" className="secondary" disabled={revisionOffset === 0} onClick={() => { setRevisionId(""); setRevisionOffset((value) => Math.max(0, value - 200)); }}>Previous revisions</button>
      <button type="button" className="secondary" disabled={revisionOffset + 200 >= revisionPage.total} onClick={() => { setRevisionId(""); setRevisionOffset((value) => value + 200); }}>Next revisions</button>
    </div> : null}
    <details open={pending.length > 0} className="measure-selection">
      <summary>All selected requirements ({pending.length})</summary>
      {pending.length ? <ul>{pending.map((item) => <li key={`${item.catalog_id}:${item.revision_id}:${item.control_id}`}>
        {catalogs.find((option) => option.id === item.catalog_id)?.name ?? item.catalog_id} · revision {revisionNumbers[item.revision_id] ?? item.revision_id} · {item.control_id}
        {titles[`${item.catalog_id}:${item.revision_id}`]?.[item.control_id] ? ` — ${titles[`${item.catalog_id}:${item.revision_id}`][item.control_id]}` : ""}
        {" "}<button type="button" className="secondary" onClick={() => updatePending(pending.filter((other) => other !== item))}>Remove</button>
      </li>)}</ul> : <p className="muted">No requirements selected.</p>}
    </details>
    {catalogId && revisionId ? <MappingControlPicker key={key} tenantId={tenantId} catalogId={catalogId}
      revisionId={revisionId} label={catalog?.name ?? "Catalog"} selected={selected.map((item) => item.control_id)}
      unavailable={unavailable.map((item) => item.control_id)} disabled={false} onControlTitles={reportTitles}
      onChange={(ids) => updatePending([
        ...pending.filter((item) => item.catalog_id !== catalogId || item.revision_id !== revisionId),
        ...ids.filter((id) => !unavailable.some((item) => item.control_id === id)).map((control_id) => ({
          catalog_id: catalogId, revision_id: revisionId, control_id, description: "",
        })),
      ])} /> : <p className="muted">Select a catalog revision to browse requirements.</p>}
  </section>;
}
