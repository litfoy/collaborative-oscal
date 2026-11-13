"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { bffGet } from "@/lib/bff-client";
import { indexBrowser } from "@/lib/profile-browser";
import type { ProfileBrowserNode } from "@/lib/types";

const PAGE_SIZE = 50;

export function MappingControlPicker({
  tenantId,
  catalogId,
  revisionId,
  label,
  selected,
  onChange,
  disabled,
}: {
  tenantId: string;
  catalogId: string;
  revisionId: string;
  label: string;
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled: boolean;
}) {
  const [loaded, setLoaded] = useState<{ base: string; nodes: ProfileBrowserNode[]; error: string | null } | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const base = `tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}`;

  useEffect(() => {
    const controller = new AbortController();
    bffGet<{ nodes: ProfileBrowserNode[] }>(`${base}/profile-browser`, undefined, controller.signal)
      .then((result) => setLoaded({ base, nodes: result.nodes, error: null }))
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setLoaded({
            base,
            nodes: [],
            error: cause instanceof Error ? cause.message : "Unable to load catalog controls.",
          });
        }
      });
    return () => controller.abort();
  }, [base]);

  const nodes = loaded?.base === base ? loaded.nodes : [];
  const error = loaded?.base === base ? loaded.error : null;
  const loading = loaded?.base !== base;
  const index = useMemo(() => indexBrowser(nodes), [nodes]);
  const results = useMemo(() => index.controls.filter((node) =>
    (index.search.get(node.key) ?? "").includes(deferredQuery),
  ), [index, deferredQuery]);
  const pageCount = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = results.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

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
    <fieldset className="mapping-control-picker" disabled={disabled}>
      <legend>{label} controls ({selected.length} selected)</legend>
      <label className="field">
        Search {label.toLocaleLowerCase()} controls
        <input type="search" value={query} maxLength={200} placeholder="Control ID, title or requirement text"
          onChange={(event) => { setQuery(event.target.value); setPage(0); }} />
      </label>
      {error ? <p role="alert" className="alert">{error}</p> : null}
      {loading ? <p role="status">Loading controls from the selected revision…</p> : null}
      {!loading && !error ? <p role="status">{results.length} matching controls · {selected.length} selected</p> : null}
      {selected.length > 0 ? <ul className="mapping-selected-controls">
        {selected.map((id) => <li key={id}><span className="mono">{id}</span>
          <button type="button" className="secondary" disabled={disabled} onClick={() => toggle(id, false)} aria-label={`Remove ${id}`}>Remove</button>
        </li>)}
      </ul> : null}
      <ul className="requirement-list">
        {visible.map((node) => {
          if (!node.id) return null;
          const controlId = node.id;
          return <li key={node.key} className="requirement">
            <label className="requirement-select">
              <input type="checkbox" checked={selected.includes(controlId)}
                onChange={(event) => toggle(controlId, event.target.checked)} />
              <span><span className="mono">{controlId}</span> <strong>{node.title}</strong>
                {location(node) ? <span className="muted mapping-control-location">{location(node)}</span> : null}
              </span>
            </label>
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
