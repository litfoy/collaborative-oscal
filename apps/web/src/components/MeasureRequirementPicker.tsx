// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { MappingControlPicker } from "@/components/MappingControlPicker";
import { bffGet } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
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
  const { t, number, enumLabel, errorMessage } = useI18n();
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
        if (!controller.signal.aborted) setError(errorMessage(cause) || t("measures.loadRevisionsError"));
      });
    return () => controller.abort();
  }, [tenantId, catalogId, revisionOffset, errorMessage, t]);

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
      setError(errorMessage(cause) || t("measures.loadCatalogsError"));
    } finally {
      setLoading(false);
    }
  }

  return <section className="panel measure-picker">
    <div className="workspace-actions measure-heading">
      <div><h2 ref={heading} tabIndex={-1}>{t("measures.addRequirementsTitle")}</h2><p className="muted">{t("measures.selectExplicitRequirements")}</p></div>
      <button type="button" className="secondary" onClick={onCancel}>{t("measures.cancel")}</button>
      <button type="button" disabled={!pending.length} onClick={() => onConfirm(pending)}>{t("measures.addSelected", { count: number(pending.length) })}</button>
    </div>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <div className="mapping-control-filters">
      <label className="field">{t("measures.catalog")}
        <select value={catalogId} onChange={(event) => {
          setCatalogId(event.target.value); setRevisionId(""); setRevisionPage(null); setRevisionOffset(0);
        }}>
          <option value="">{t("measures.selectCatalog")}</option>
          {catalogs.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      <label className="field">{t("measures.catalogRevision")}
        <select value={revisionId} onChange={(event) => setRevisionId(event.target.value)}>
          <option value="">{t("measures.selectRevision")}</option>
          {revisionPage?.items.map((item) => <option key={item.id} value={item.id}>
            {t("measures.revision", { number: number(item.revision_number) })} · {enumLabel(item.lifecycle_status)}
          </option>)}
        </select>
      </label>
    </div>
    {catalogs.length < catalogTotal ? <button type="button" className="secondary" disabled={loading} onClick={() => void loadMoreCatalogs()}>
      {loading ? t("measures.loading") : t("measures.loadMoreCatalogs")}
    </button> : null}
    {revisionPage && revisionPage.total > 200 ? <div className="workspace-actions">
      <button type="button" className="secondary" disabled={revisionOffset === 0} onClick={() => { setRevisionId(""); setRevisionOffset((value) => Math.max(0, value - 200)); }}>{t("measures.previousRevisions")}</button>
      <button type="button" className="secondary" disabled={revisionOffset + 200 >= revisionPage.total} onClick={() => { setRevisionId(""); setRevisionOffset((value) => value + 200); }}>{t("measures.nextRevisions")}</button>
    </div> : null}
    <details open={pending.length > 0} className="measure-selection">
      <summary>{t("measures.allSelectedRequirements", { count: number(pending.length) })}</summary>
      {pending.length ? <ul>{pending.map((item) => {
        const revisionNumber = revisionNumbers[item.revision_id];
        return <li key={`${item.catalog_id}:${item.revision_id}:${item.control_id}`}>
          {catalogs.find((option) => option.id === item.catalog_id)?.name ?? item.catalog_id} · {
            revisionNumber === undefined
              ? t("measures.revisionId", { id: item.revision_id })
              : t("measures.revisionNumber", { number: number(revisionNumber) })
          } · {item.control_id}
          {titles[`${item.catalog_id}:${item.revision_id}`]?.[item.control_id] ? ` — ${titles[`${item.catalog_id}:${item.revision_id}`][item.control_id]}` : ""}
          {" "}<button type="button" className="secondary" onClick={() => updatePending(pending.filter((other) => other !== item))}>{t("measures.remove")}</button>
        </li>;
      })}</ul> : <p className="muted">{t("measures.noRequirementsSelected")}</p>}
    </details>
    {catalogId && revisionId ? <MappingControlPicker key={key} tenantId={tenantId} catalogId={catalogId}
      revisionId={revisionId} label={catalog?.name ?? "Catalog"} selected={selected.map((item) => item.control_id)}
      unavailable={unavailable.map((item) => item.control_id)} disabled={false} onControlTitles={reportTitles}
      onChange={(ids) => updatePending([
        ...pending.filter((item) => item.catalog_id !== catalogId || item.revision_id !== revisionId),
        ...ids.filter((id) => !unavailable.some((item) => item.control_id === id)).map((control_id) => ({
          catalog_id: catalogId, revision_id: revisionId, control_id, description: "",
        })),
      ])} /> : <p className="muted">{t("measures.selectRevisionToBrowse")}</p>}
  </section>;
}
