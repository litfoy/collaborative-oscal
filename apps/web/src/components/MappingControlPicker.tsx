"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";

import { bffGet } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
import { inBranch, indexBrowser, matchesProperties } from "@/lib/profile-browser";
import type { ControlDetail, ProfileBrowserNode } from "@/lib/types";

import { ControlDetailView } from "./ControlDetailView";

const PAGE_SIZE = 50;
const EMPTY_NODES: ProfileBrowserNode[] = [];

export function MappingControlPicker({
  tenantId,
  catalogId,
  revisionId,
  label,
  selected,
  onChange,
  onControlTitles,
  disabled,
  unavailable = [],
}: {
  tenantId: string;
  catalogId: string;
  revisionId: string;
  label: string;
  selected: string[];
  onChange: (ids: string[]) => void;
  onControlTitles: (titles: Record<string, string>) => void;
  disabled: boolean;
  unavailable?: string[];
}) {
  const { t, number, errorMessage } = useI18n();
  const [loaded, setLoaded] = useState<{ base: string; attempt: number; nodes: ProfileBrowserNode[]; error: string | null } | null>(null);
  const [query, setQuery] = useState("");
  const [branch, setBranch] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const base = `tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}`;

  useEffect(() => {
    const controller = new AbortController();
    bffGet<{ nodes: ProfileBrowserNode[] }>(`${base}/profile-browser`, undefined, controller.signal)
      .then((result) => setLoaded({ base, attempt, nodes: result.nodes, error: null }))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setLoaded({
            base,
            attempt,
            nodes: [],
            error: errorMessage(cause) || t("mappings.loadControlsError"),
          });
        }
      });
    return () => controller.abort();
  }, [base, attempt, errorMessage, t]);

  const nodes = loaded?.base === base && loaded.attempt === attempt ? loaded.nodes : EMPTY_NODES;
  const error = loaded?.base === base && loaded.attempt === attempt ? loaded.error : null;
  const loading = loaded?.base !== base || loaded.attempt !== attempt;
  const index = useMemo(() => indexBrowser(nodes), [nodes]);
  const groups = useMemo(() => nodes.filter((node) => node.kind === "group"), [nodes]);
  const controlTitles = useMemo(() => Object.fromEntries(
    index.controls.flatMap((node) => node.id ? [[node.id, node.title]] : []),
  ), [index.controls]);
  const results = useMemo(() => index.controls.filter((node) =>
    inBranch(node, branch || null) && matchesProperties(node, filters) &&
      (index.search.get(node.key) ?? "").includes(deferredQuery),
  ), [index, deferredQuery, branch, filters]);
  const pageCount = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = results.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  useEffect(() => onControlTitles(controlTitles), [controlTitles, onControlTitles]);

  function location(node: ProfileBrowserNode): string {
    const ancestors: string[] = [];
    let parent = node.parent_key;
    while (parent) {
      const ancestor = index.byKey.get(parent);
      if (!ancestor) break;
      ancestors.unshift(ancestor.title);
      parent = ancestor.parent_key;
    }
    return ancestors.join(" › ");
  }

  function toggle(id: string, checked: boolean) {
    onChange(checked ? [...selected, id] : selected.filter((item) => item !== id));
  }

  return (
    <fieldset className="mapping-control-picker">
      <legend>{label} controls ({t("mappings.controlCount", { count: number(selected.length) })})</legend>
      <div className="mapping-control-filters">
        <label className="field">
          {t("mappings.searchControls", { name: label.toLocaleLowerCase() })}
          <input type="search" value={query} maxLength={200} placeholder={t("mappings.controlSearchPlaceholder")}
            onChange={(event) => { setQuery(event.target.value); setPage(0); }} />
        </label>
        <label className="field">{t("mappings.catalogSection", { name: label })}
          <select value={branch} onChange={(event) => { setBranch(event.target.value); setPage(0); }}>
            <option value="">{t("mappings.allCatalogSections")}</option>
            {groups.map((group) => <option key={group.key} value={group.key}>
              {location(group) ? `${location(group)} › ` : ""}{group.title}
            </option>)}
          </select>
        </label>
      </div>
      {index.facets.length ? <details>
        <summary>{t("mappings.catalogFilters")}</summary>
        <div className="mapping-control-filters">
          {index.facets.map((facet) => <label className="field" key={facet.key}>
            {facet.label}{facet.ns ? ` (${facet.ns})` : ""}
            <select value={filters[facet.key] ?? ""} onChange={(event) => {
              setFilters((current) => ({ ...current, [facet.key]: event.target.value }));
              setPage(0);
            }}>
              <option value="">{t("mappings.all")}</option>
              {[...facet.values].sort().map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>)}
        </div>
      </details> : null}
      {error ? <p role="alert" className="alert">{error}{" "}
        <button type="button" className="secondary" onClick={() => setAttempt((value) => value + 1)}>{t("mappings.retryControls")}</button>
      </p> : null}
      {loading ? <p role="status">{t("mappings.loadingControls")}</p> : null}
      {!loading && !error ? <p role="status">{t(results.length === 1 ? "mappings.matchingControlOne" : "mappings.matchingControlOther", { count: number(results.length), selected: number(selected.length) })}</p> : null}
      <section className="mapping-selection-summary" aria-label={t("mappings.selectedControlsAria", { name: label })}>
        <div className="workspace-actions">
          <strong>{t(selected.length === 1 ? "mappings.selectedControlOne" : "mappings.selectedControlOther", { name: label.toLocaleLowerCase(), count: number(selected.length) })}</strong>
          {selected.length > 0 ? <button type="button" className="secondary" disabled={disabled}
            onClick={() => onChange([])}>{t("mappings.clearSelection")}</button> : null}
        </div>
        {selected.length > 0 ? <ul className="mapping-selected-controls">
          {selected.map((id) => <li key={id}>
            <span><span className="mono">{id}</span>{controlTitles[id] ? ` — ${controlTitles[id]}` : ""}</span>
            <button type="button" className="secondary" disabled={disabled} onClick={() => toggle(id, false)}
              aria-label={t("mappings.removeControlAria", { control: id, name: label.toLocaleLowerCase() })}>{t("mappings.remove")}</button>
          </li>)}
        </ul> : <p className="muted">{t("mappings.noControlsSelected")}</p>}
      </section>
      <ul className="requirement-list">
        {visible.map((node) => {
          if (!node.id) return null;
          const controlId = node.id;
          return <li key={node.key} className={selected.includes(controlId) ? "requirement selected" : "requirement"}>
            <label className="requirement-select">
              <input type="checkbox" checked={selected.includes(controlId)} disabled={disabled || unavailable.includes(controlId)}
                onChange={(event) => toggle(controlId, event.target.checked)} />
              <span><span className="mono">{controlId}</span> <strong>{node.title}</strong>
                {unavailable.includes(controlId) ? t("mappings.alreadyAssociated") : null}
                {location(node) ? <span className="muted mapping-control-location">{location(node)}</span> : null}
              </span>
            </label>
            {node.text ? <p className="requirement-summary">{node.text}</p> : null}
            <MappingControlDetails tenantId={tenantId} catalogId={catalogId} revisionId={revisionId}
              controlId={controlId} />
          </li>;
        })}
      </ul>
      {pageCount > 1 ? <nav className="pagination" aria-label={t("mappings.controlResultsAria", { name: label })}>
        <button type="button" className="secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>{t("mappings.previous")}</button>
        <span>{t("mappings.page", { current: number(currentPage + 1), total: number(pageCount) })}</span>
        <button type="button" className="secondary" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>{t("mappings.next")}</button>
      </nav> : null}
    </fieldset>
  );
}

export function MappingControlDetails({
  tenantId, catalogId, revisionId, controlId,
}: {
  tenantId: string;
  catalogId: string;
  revisionId: string;
  controlId: string;
}) {
  const { t, errorMessage } = useI18n();
  const [control, setControl] = useState<ControlDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const path = `tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}/controls/${encodeURIComponent(controlId)}`;

  useEffect(() => {
    return () => request.current?.abort();
  }, []);

  function toggleDetails(event: SyntheticEvent<HTMLDetailsElement>) {
    const isOpen = event.currentTarget.open;
    if (!isOpen || control || loading || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    bffGet<ControlDetail>(path, undefined, controller.signal).then((result) => {
      if (!controller.signal.aborted) setControl(result);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(cause) || t("mappings.loadControlDefinitionError"));
    }).finally(() => {
      if (!controller.signal.aborted) {
        request.current = null;
        setLoading(false);
      }
    });
  }

  return <details className="mapping-control-detail" onToggle={toggleDetails}>
    <summary>{t("mappings.viewControlDefinition")}</summary>
    {loading ? <p role="status">{t("mappings.loadingControlDefinition")}</p> : null}
    {error ? <p role="alert" className="alert">{error} {t("mappings.retryControlDefinition")}</p> : null}
    {control ? <ControlDetailView control={control} presentation="profile" /> : null}
  </details>;
}
