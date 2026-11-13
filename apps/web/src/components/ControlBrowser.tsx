"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { bffGet } from "@/lib/bff-client";
import { ApiError, ERROR_MESSAGES } from "@/lib/errors";
import type { ControlDetail, ControlListItem, OutlineNode, Paged, RelatedMapping } from "@/lib/types";

import { ControlDetailView } from "./ControlDetailView";

interface Props {
  tenantId: string;
  catalogId: string;
  revisionId: string;
  initialRoot: Paged<OutlineNode>;
  initialControl: ControlDetail | null;
}

interface Children {
  items: OutlineNode[];
  total: number;
  loading: boolean;
}

type Row =
  | { type: "node"; node: OutlineNode; key: string; parent: string; level: number; index: number; size: number }
  | { type: "more"; key: string; parent: string; level: number };

const PAGE = 100;
const ROOT = "root";

function nodeKey(node: OutlineNode): string {
  return `${node.kind}:${node.id}`;
}

export function ControlBrowser({ tenantId, catalogId, revisionId, initialRoot, initialControl }: Props) {
  const base = `tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}`;
  const searchId = useId();
  const treeLabelId = useId();

  const [children, setChildren] = useState<Record<string, Children>>({
    [ROOT]: { items: initialRoot.items, total: initialRoot.total, loading: false },
  });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [focusKey, setFocusKey] = useState<string | null>(
    initialRoot.items[0] ? nodeKey(initialRoot.items[0]) : null,
  );
  const [selected, setSelected] = useState<string | null>(initialControl?.oscal_control_id ?? null);
  const [detail, setDetail] = useState<ControlDetail | null>(initialControl);
  const [relatedByControl, setRelatedByControl] = useState<Record<string, { items: RelatedMapping[]; error: string | null }>>({});
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [results, setResults] = useState<Paged<ControlListItem> | null>(null);
  const [searching, setSearching] = useState(false);
  const itemRefs = useRef<Map<string, HTMLElement>>(new Map());
  const detailRequest = useRef(0);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    bffGet<{ items: RelatedMapping[] }>(
      `${base}/controls/${encodeURIComponent(selected)}/related-mappings`,
      undefined,
      controller.signal,
    ).then((result) => setRelatedByControl((current) => ({
      ...current,
      [selected]: { items: result.items, error: null },
    }))).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setRelatedByControl((current) => ({
          ...current,
          [selected]: {
            items: [],
            error: cause instanceof Error ? cause.message : "Unable to load related mappings.",
          },
        }));
      }
    });
    return () => controller.abort();
  }, [base, selected]);
  const related = selected ? relatedByControl[selected] : undefined;

  const fail = useCallback((cause: unknown) => {
    setError(
      cause instanceof ApiError ? cause : new ApiError("unavailable", 0, ERROR_MESSAGES.unavailable),
    );
  }, []);

  const rows = useMemo(() => {
    const result: Row[] = [];
    const walk = (parent: string, level: number) => {
      const group = children[parent];
      if (!group) return;
      group.items.forEach((node, index) => {
        const key = nodeKey(node);
        result.push({ type: "node", node, key, parent, level, index, size: group.items.length });
        if (expanded.has(key)) walk(key, level + 1);
      });
      if (group.items.length < group.total) {
        result.push({ type: "more", key: `more:${parent}`, parent, level });
      }
    };
    walk(ROOT, 1);
    return result;
  }, [children, expanded]);

  const loadChildren = useCallback(
    async (parent: string, node: OutlineNode | null) => {
      const current = children[parent];
      if (current?.loading) return;
      const offset = current?.items.length ?? 0;
      setChildren((state) => ({
        ...state,
        [parent]: { items: current?.items ?? [], total: current?.total ?? 0, loading: true },
      }));
      try {
        const page = await bffGet<Paged<OutlineNode>>(`${base}/outline`, {
          parent_kind: node?.kind,
          parent_id: node?.id,
          limit: PAGE,
          offset,
        });
        setChildren((state) => ({
          ...state,
          [parent]: { items: [...(current?.items ?? []), ...page.items], total: page.total, loading: false },
        }));
      } catch (cause) {
        setChildren((state) => ({
          ...state,
          [parent]: { items: current?.items ?? [], total: current?.total ?? 0, loading: false },
        }));
        fail(cause);
      }
    },
    [base, children, fail],
  );

  const selectControl = useCallback(
    async (oscalId: string) => {
      const request = ++detailRequest.current;
      setSelected(oscalId);
      setError(null);
      setDetailLoading(true);
      try {
        const control = await bffGet<ControlDetail>(`${base}/controls/${encodeURIComponent(oscalId)}`);
        if (request !== detailRequest.current) return;
        setDetail(control);
        const url = new URL(window.location.href);
        url.searchParams.set("revision", revisionId);
        url.searchParams.set("control", oscalId);
        window.history.replaceState(null, "", url);
      } catch (cause) {
        if (request === detailRequest.current) fail(cause);
      } finally {
        if (request === detailRequest.current) setDetailLoading(false);
      }
    },
    [base, fail, revisionId],
  );

  const toggle = useCallback(
    (row: Extract<Row, { type: "node" }>) => {
      const next = new Set(expanded);
      if (next.has(row.key)) {
        next.delete(row.key);
      } else {
        next.add(row.key);
        if (!children[row.key]) void loadChildren(row.key, row.node);
      }
      setExpanded(next);
    },
    [children, expanded, loadChildren],
  );

  const focusRow = (key: string) => {
    setFocusKey(key);
    itemRefs.current.get(key)?.focus();
  };

  const activate = (row: Row) => {
    if (row.type === "more") {
      const parentRow = rows.find((candidate) => candidate.key === row.parent);
      void loadChildren(row.parent, parentRow?.type === "node" ? parentRow.node : null);
      return;
    }
    if (row.node.kind === "control") void selectControl(row.node.oscal_id ?? "");
    if (row.node.child_count > 0) toggle(row);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = rows.findIndex((row) => row.key === focusKey);
    const row = rows[index];
    if (!row) return;
    const move = (target: Row | undefined) => {
      if (target) {
        event.preventDefault();
        focusRow(target.key);
      }
    };
    switch (event.key) {
      case "ArrowDown":
        return move(rows[index + 1]);
      case "ArrowUp":
        return move(rows[index - 1]);
      case "Home":
        return move(rows[0]);
      case "End":
        return move(rows[rows.length - 1]);
      case "ArrowRight":
        if (row.type === "node" && row.node.child_count > 0) {
          event.preventDefault();
          if (!expanded.has(row.key)) toggle(row);
          else move(rows[index + 1]);
        }
        return;
      case "ArrowLeft":
        if (row.type === "node" && expanded.has(row.key)) {
          event.preventDefault();
          toggle(row);
        } else {
          move(rows.find((candidate) => candidate.key === row.parent));
        }
        return;
      case "Enter":
      case " ":
        event.preventDefault();
        activate(row);
        return;
    }
  };

  const runSearch = async (term: string, append: boolean) => {
    setSearching(true);
    setError(null);
    try {
      const offset = append && results ? results.items.length : 0;
      const page = await bffGet<Paged<ControlListItem>>(`${base}/controls`, {
        q: term,
        limit: 50,
        offset,
      });
      setResults(append && results ? { ...page, items: [...results.items, ...page.items] } : page);
      setActiveQuery(term);
    } catch (cause) {
      fail(cause);
    } finally {
      setSearching(false);
    }
  };

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const term = query.trim();
    if (!term) {
      clearSearch();
      return;
    }
    void runSearch(term, false);
  };

  const clearSearch = () => {
    setQuery("");
    setActiveQuery(null);
    setResults(null);
  };

  return (
    <div className="explorer">
      <div className="panel tree-panel">
        <form role="search" className="search-form" onSubmit={submitSearch}>
          <div className="field">
            <label htmlFor={searchId}>Search controls</label>
            <input
              id={searchId}
              type="search"
              value={query}
              placeholder="ID or title"
              maxLength={200}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <button type="submit" disabled={searching}>
            Search
          </button>
          {activeQuery !== null ? (
            <button type="button" className="secondary" onClick={clearSearch}>
              Clear
            </button>
          ) : null}
        </form>

        {error ? <ErrorNotice error={error} /> : null}

        {activeQuery !== null && results ? (
          <section aria-label="Search results">
            <p role="status">
              {results.total === 0
                ? `No controls match “${activeQuery}”.`
                : `${results.total} control${results.total === 1 ? "" : "s"} match “${activeQuery}”.`}
            </p>
            <ul className="result-list">
              {results.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-current={selected === item.oscal_control_id ? "true" : undefined}
                    onClick={() => void selectControl(item.oscal_control_id)}
                  >
                    <span className="tree-id">{item.oscal_control_id}</span> {item.title}
                    {item.group ? <span className="muted"> · {item.group.oscal_group_id ?? item.group.title}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
            {results.items.length < results.total ? (
              <button type="button" className="secondary" onClick={() => void runSearch(activeQuery, true)}>
                Load more results
              </button>
            ) : null}
          </section>
        ) : (
          <>
            <h2 id={treeLabelId} className="visually-hidden">
              Control hierarchy
            </h2>
            {rows.length === 0 ? (
              <p className="muted">This revision contains no controls.</p>
            ) : (
              <div role="tree" aria-labelledby={treeLabelId} onKeyDown={onKeyDown}>
                {rows.map((row) => (
                  <TreeRow
                    key={row.key}
                    row={row}
                    expanded={expanded.has(row.key)}
                    loading={children[row.key]?.loading ?? false}
                    selected={row.type === "node" && row.node.kind === "control" && row.node.oscal_id === selected}
                    focusable={row.key === (focusKey ?? rows[0].key)}
                    register={(element) => {
                      if (element) itemRefs.current.set(row.key, element);
                      else itemRefs.current.delete(row.key);
                    }}
                    onFocus={() => setFocusKey(row.key)}
                    onClick={() => {
                      setFocusKey(row.key);
                      activate(row);
                    }}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div aria-live="polite" aria-busy={detailLoading}>
        {detailLoading ? <p className="panel">Loading control…</p> : null}
        {!detailLoading && detail ? <ControlDetailView control={detail} relatedMappings={related?.items ?? []}
          tenantId={tenantId} relatedError={related?.error ?? null} relatedLoading={related === undefined} /> : null}
        {!detailLoading && !detail ? (
          <div className="empty">Select a control to read its details.</div>
        ) : null}
      </div>
    </div>
  );
}

function TreeRow({
  row,
  expanded,
  loading,
  selected,
  focusable,
  register,
  onFocus,
  onClick,
}: {
  row: Row;
  expanded: boolean;
  loading: boolean;
  selected: boolean;
  focusable: boolean;
  register: (element: HTMLElement | null) => void;
  onFocus: () => void;
  onClick: () => void;
}) {
  const indent = { paddingLeft: `${(row.level - 1) * 1.1}rem` };
  if (row.type === "more") {
    return (
      <div
        role="treeitem"
        aria-level={row.level}
        aria-selected={false}
        tabIndex={focusable ? 0 : -1}
        ref={register}
        className="tree-row"
        style={indent}
        onFocus={onFocus}
        onClick={onClick}
      >
        <span className="tree-toggle" aria-hidden="true" />
        Load more…
      </div>
    );
  }
  const { node } = row;
  const expandable = node.child_count > 0;
  return (
    <div
      role="treeitem"
      aria-level={row.level}
      aria-posinset={row.index + 1}
      aria-setsize={row.size}
      aria-expanded={expandable ? expanded : undefined}
      aria-selected={selected}
      aria-busy={loading}
      tabIndex={focusable ? 0 : -1}
      ref={register}
      className="tree-row"
      style={indent}
      onFocus={onFocus}
      onClick={onClick}
    >
      <span className="tree-toggle" aria-hidden="true">
        {expandable ? (expanded ? "▾" : "▸") : ""}
      </span>
      {node.oscal_id ? <span className="tree-id">{node.oscal_id}</span> : null}
      <span>{node.title}</span>
      {node.kind === "group" ? <span className="visually-hidden"> (group)</span> : null}
    </div>
  );
}

function ErrorNotice({ error }: { error: ApiError }) {
  return (
    <p role="alert" className="alert">
      {error.message}{" "}
      {error.kind === "session_expired" ? <a href="/auth/login">Sign in again</a> : null}
    </p>
  );
}
