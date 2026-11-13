"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState, type SyntheticEvent } from "react";

import { bffGet } from "@/lib/bff-client";
import { inBranch, indexBrowser } from "@/lib/profile-browser";
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
}: {
  tenantId: string;
  catalogId: string;
  revisionId: string;
  label: string;
  selected: string[];
  onChange: (ids: string[]) => void;
  onControlTitles: (titles: Record<string, string>) => void;
  disabled: boolean;
}) {
  const [loaded, setLoaded] = useState<{ base: string; attempt: number; nodes: ProfileBrowserNode[]; error: string | null } | null>(null);
  const [query, setQuery] = useState("");
  const [branch, setBranch] = useState("");
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
            error: cause instanceof Error ? cause.message : "Unable to load catalog controls.",
          });
        }
      });
    return () => controller.abort();
  }, [base, attempt]);

  const nodes = loaded?.base === base && loaded.attempt === attempt ? loaded.nodes : EMPTY_NODES;
  const error = loaded?.base === base && loaded.attempt === attempt ? loaded.error : null;
  const loading = loaded?.base !== base || loaded.attempt !== attempt;
  const index = useMemo(() => indexBrowser(nodes), [nodes]);
  const groups = useMemo(() => nodes.filter((node) => node.kind === "group"), [nodes]);
  const controlTitles = useMemo(() => Object.fromEntries(
    index.controls.flatMap((node) => node.id ? [[node.id, node.title]] : []),
  ), [index.controls]);
  const results = useMemo(() => index.controls.filter((node) =>
    inBranch(node, branch || null) && (index.search.get(node.key) ?? "").includes(deferredQuery),
  ), [index, deferredQuery, branch]);
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
      <legend>{label} controls ({selected.length} selected)</legend>
      <div className="mapping-control-filters">
        <label className="field">
          Search {label.toLocaleLowerCase()} controls
          <input type="search" value={query} maxLength={200} placeholder="Control ID, title or requirement text"
            onChange={(event) => { setQuery(event.target.value); setPage(0); }} />
        </label>
        <label className="field">Catalog section · {label}
          <select value={branch} onChange={(event) => { setBranch(event.target.value); setPage(0); }}>
            <option value="">All catalog sections</option>
            {groups.map((group) => <option key={group.key} value={group.key}>
              {location(group) ? `${location(group)} › ` : ""}{group.title}
            </option>)}
          </select>
        </label>
      </div>
      {error ? <p role="alert" className="alert">{error}{" "}
        <button type="button" className="secondary" onClick={() => setAttempt((value) => value + 1)}>Retry controls</button>
      </p> : null}
      {loading ? <p role="status">Loading controls from the selected revision…</p> : null}
      {!loading && !error ? <p role="status">{results.length} matching controls · {selected.length} selected</p> : null}
      <section className="mapping-selection-summary" aria-label={`${label} selected controls`}>
        <div className="workspace-actions">
          <strong>Selected {label.toLocaleLowerCase()} controls ({selected.length})</strong>
          {selected.length > 0 ? <button type="button" className="secondary" disabled={disabled}
            onClick={() => onChange([])}>Clear selection</button> : null}
        </div>
        {selected.length > 0 ? <ul className="mapping-selected-controls">
          {selected.map((id) => <li key={id}>
            <span><span className="mono">{id}</span>{controlTitles[id] ? ` — ${controlTitles[id]}` : ""}</span>
            <button type="button" className="secondary" disabled={disabled} onClick={() => toggle(id, false)}
              aria-label={`Remove ${id} from ${label.toLocaleLowerCase()} selection`}>Remove</button>
          </li>)}
        </ul> : <p className="muted">No controls selected.</p>}
      </section>
      <ul className="requirement-list">
        {visible.map((node) => {
          if (!node.id) return null;
          const controlId = node.id;
          return <li key={node.key} className={selected.includes(controlId) ? "requirement selected" : "requirement"}>
            <label className="requirement-select">
              <input type="checkbox" checked={selected.includes(controlId)} disabled={disabled}
                onChange={(event) => toggle(controlId, event.target.checked)} />
              <span><span className="mono">{controlId}</span> <strong>{node.title}</strong>
                {location(node) ? <span className="muted mapping-control-location">{location(node)}</span> : null}
              </span>
            </label>
            {node.text ? <p className="requirement-summary">{node.text}</p> : null}
            <MappingControlDetails tenantId={tenantId} catalogId={catalogId} revisionId={revisionId}
              controlId={controlId} />
          </li>;
        })}
      </ul>
      {pageCount > 1 ? <nav className="pagination" aria-label={`${label} control results`}>
        <button type="button" className="secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
        <span>Page {currentPage + 1} of {pageCount}</span>
        <button type="button" className="secondary" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>Next</button>
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
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load this control definition.");
    }).finally(() => {
      if (!controller.signal.aborted) {
        request.current = null;
        setLoading(false);
      }
    });
  }

  return <details className="mapping-control-detail" onToggle={toggleDetails}>
    <summary>View full control definition</summary>
    {loading ? <p role="status">Loading control definition…</p> : null}
    {error ? <p role="alert" className="alert">{error} Close and reopen this section to retry.</p> : null}
    {control ? <ControlDetailView control={control} presentation="profile" /> : null}
  </details>;
}
