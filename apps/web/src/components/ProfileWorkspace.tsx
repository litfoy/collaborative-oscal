"use client";

import { useDeferredValue, useEffect, useMemo, useState, type CSSProperties } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import { ApiError, ERROR_MESSAGES } from "@/lib/errors";
import { renderProse } from "@/lib/safe";
import { inBranch, indexBrowser, matchesProperties, MAX_PROFILE_CONTROLS, propertyLabel } from "@/lib/profile-browser";
import type { ControlDetail, Profile, ProfileBrowserNode, RevisionDetail } from "@/lib/types";

import { ControlDetailView } from "./ControlDetailView";

const PAGE_SIZE = 50;
const PREVIEW_PARAMETERS = new Map<string, string>();
const VIEWS = ["Catalog Browser", "Selected Requirements", "Profile Settings"] as const;
type WorkspaceView = typeof VIEWS[number];

export function ProfileWorkspace({
  tenantId, initialProfile, isNew, catalogName, canWrite, onClose, onSaved,
}: {
  tenantId: string;
  initialProfile: Profile;
  isNew: boolean;
  catalogName: string;
  canWrite: boolean;
  onClose: () => void;
  onSaved: (profile: Profile) => void;
}) {
  const [saved, setSaved] = useState<Profile | null>(isNew ? null : initialProfile);
  const [title, setTitle] = useState(initialProfile.title);
  const [description, setDescription] = useState(initialProfile.description ?? "");
  const [selected, setSelected] = useState(new Set(initialProfile.control_ids));
  const [data, setData] = useState<{ nodes: ProfileBrowserNode[]; revision: RevisionDetail } | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<WorkspaceView>("Catalog Browser");
  const [showNavigation, setShowNavigation] = useState(true);
  const [showDetails, setShowDetails] = useState(true);
  const [navigationWidth, setNavigationWidth] = useState(18);
  const [detailWidth, setDetailWidth] = useState(26);
  const [selectionQuery, setSelectionQuery] = useState("");
  const deferredSelectionQuery = useDeferredValue(selectionQuery.trim().toLocaleLowerCase());
  const [selectionPage, setSelectionPage] = useState(0);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase());
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [branch, setBranch] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [navigationLimits, setNavigationLimits] = useState<Record<string, number>>({});
  const [active, setActive] = useState<string | null>(null);
  const [detailFocusRequest, setDetailFocusRequest] = useState(0);
  const [page, setPage] = useState(0);
  const base = `tenants/${tenantId}/catalogs/${initialProfile.catalog_id}/revisions/${initialProfile.revision_id}`;
  const dirty = saved
    ? title !== saved.title || description !== (saved.description ?? "") ||
      selected.size !== saved.control_ids.length || saved.control_ids.some((id) => !selected.has(id))
    : title !== "" || description !== "" || selected.size > 0;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      bffGet<{ nodes: ProfileBrowserNode[] }>(`${base}/profile-browser`, undefined, controller.signal),
      bffGet<RevisionDetail>(base, undefined, controller.signal),
    ]).then(([browser, revision]) => {
      if (!controller.signal.aborted) {
        setData({ nodes: browser.nodes, revision });
        setLoadError(null);
      }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setLoadError(messageFor(cause));
    });
    return () => controller.abort();
  }, [base, loadAttempt]);

  useEffect(() => {
    if (!dirty && !busy) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (!link || link.getAttribute("href")?.startsWith("#") ||
          link.getAttribute("target") === "_blank" || link.hasAttribute("download") ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      if (busy || !window.confirm("Discard unsaved profile changes?")) event.preventDefault();
    };
    const submit = (event: SubmitEvent) => {
      if (busy || !window.confirm("Discard unsaved profile changes?")) event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    document.addEventListener("submit", submit, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", navigate, true);
      document.removeEventListener("submit", submit, true);
    };
  }, [dirty, busy]);

  const index = useMemo(() => indexBrowser(data?.nodes ?? []), [data]);
  const results = useMemo(() => index.controls.filter((node) =>
    inBranch(node, branch) && (index.search.get(node.key) ?? "").includes(deferredQuery) && matchesProperties(node, filters),
  ), [index, branch, deferredQuery, filters]);
  const pageCount = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = results.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const selectedResults = useMemo(() => index.controls.filter((node) =>
    node.id && selected.has(node.id) && (index.search.get(node.key) ?? "").includes(deferredSelectionQuery),
  ), [index, selected, deferredSelectionQuery]);
  const selectionPageCount = Math.max(1, Math.ceil(selectedResults.length / PAGE_SIZE));
  const currentSelectionPage = Math.min(selectionPage, selectionPageCount - 1);
  const selectedGroups = useMemo(() => {
    const groups = new Map<string, { title: string; nodes: ProfileBrowserNode[] }>();
    for (const node of selectedResults.slice(currentSelectionPage * PAGE_SIZE, (currentSelectionPage + 1) * PAGE_SIZE)) {
      const path: string[] = [];
      let parent = node.parent_key;
      while (parent) {
        const ancestor = index.byKey.get(parent);
        if (!ancestor) break;
        path.unshift(`${ancestor.id ? `${ancestor.id} · ` : ""}${ancestor.title}`);
        parent = ancestor.parent_key;
      }
      const key = node.parent_key ?? "root";
      const group = groups.get(key) ?? { title: path.join(" › ") || "Catalog requirements", nodes: [] };
      group.nodes.push(node);
      groups.set(key, group);
    }
    return [...groups];
  }, [index, selectedResults, currentSelectionPage]);
  const knownIds = useMemo(() => new Set(index.controls.map((node) => node.id)), [index]);
  const unknownIds = data ? [...selected].filter((id) => !knownIds.has(id)) : [];

  function changeSelection(nodes: ProfileBrowserNode[], include: boolean) {
    const next = new Set(selected);
    for (const node of nodes) if (node.id) {
      if (include) next.add(node.id);
      else next.delete(node.id);
    }
    if (next.size > MAX_PROFILE_CONTROLS) {
      setError(`A profile supports up to ${MAX_PROFILE_CONTROLS.toLocaleString()} explicitly selected requirements. Narrow your selection.`);
      return;
    }
    setSelected(next);
    setStatus(null);
    setError(null);
  }

  function navigateTo(node: ProfileBrowserNode) {
    setView("Catalog Browser");
    openDetails(node.id);
    setBranch(node.key);
    setQuery("");
    setFilters({});
    setPage(0);
    const next = new Set(expanded);
    let parent = node.parent_key;
    const limits = { ...navigationLimits };
    let target = node;
    while (true) {
      const siblings = index.children.get(target.parent_key) ?? [];
      const parentKey = target.parent_key ?? "root";
      limits[parentKey] = Math.max(limits[parentKey] ?? 100, siblings.indexOf(target) + 1);
      if (!target.parent_key) break;
      target = index.byKey.get(target.parent_key) ?? target;
    }
    while (parent) {
      next.add(parent);
      parent = index.byKey.get(parent)?.parent_key ?? null;
    }
    setExpanded(next);
    setNavigationLimits(limits);
  }

  function openDetails(id: string | null) {
    setActive(id);
    setShowDetails(true);
    setDetailFocusRequest((request) => request + 1);
  }

  useEffect(() => {
    if (detailFocusRequest > 0) document.getElementById("requirement-details")?.focus();
  }, [detailFocusRequest]);

  async function save() {
    setBusy(true);
    setError(null);
    setStatus(null);
    setSaveFailed(false);
    try {
      const body = { title: title.trim(), description, control_ids: [...selected] };
      const profile = saved
        ? await bffWrite<Profile>("PUT", `tenants/${tenantId}/profiles/${saved.id}`, body)
        : await bffWrite<Profile>("POST", `tenants/${tenantId}/profiles`, {
          ...body, catalog_id: initialProfile.catalog_id, revision_id: initialProfile.revision_id,
        });
      setSaved(profile);
      setTitle(profile.title);
      setDescription(profile.description ?? "");
      setSelected(new Set(profile.control_ids));
      onSaved(profile);
      setStatus(`Profile “${profile.title}” saved.`);
    } catch (cause) {
      setError(messageFor(cause));
      setSaveFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function tree(parent: string | null): React.ReactNode {
    const siblings = index.children.get(parent) ?? [];
    const key = parent ?? "root";
    const limit = navigationLimits[key] ?? 100;
    return <ul className="builder-tree">
      {siblings.slice(0, limit).map((node) => {
        const children = index.children.get(node.key) ?? [];
        const open = expanded.has(node.key);
        return <li key={node.key}>
          <div className="builder-tree-row">
            {children.length > 0 ? <button type="button" className="secondary tree-expander"
              aria-expanded={open} aria-label={`${open ? "Collapse" : "Expand"} ${node.id ?? node.title}`}
              onClick={() => setExpanded((current) => {
                const next = new Set(current);
                if (open) next.delete(node.key); else next.add(node.key);
                return next;
              })}>{open ? "−" : "+"}</button> : null}
            <button type="button" className="tree-location" aria-current={branch === node.key ? "location" : undefined}
              onClick={() => { setBranch(node.key); setPage(0); if (node.kind === "control") openDetails(node.id); }}>
              {node.id ? <><span className="mono">{node.id}</span>{" "}</> : null}{node.title}
              {node.kind === "control" && node.id && selected.has(node.id) ? <span className="badge">Selected</span> : null}
            </button>
          </div>
          {children.length > 0 && open ? tree(node.key) : null}
        </li>;
      })}
      {siblings.length > limit ? <li><button type="button" className="secondary"
        onClick={() => setNavigationLimits((current) => ({ ...current, [key]: limit + 100 }))}>
        Show more navigation items ({siblings.length - limit} remaining)
      </button></li> : null}
    </ul>;
  }

  return (
    <div className="profile-workspace">
      <header className="panel profile-workspace-header">
        <div className="workspace-actions">
          <button type="button" className="secondary" disabled={busy} onClick={() => {
            if (!dirty || window.confirm("Discard unsaved profile changes?")) onClose();
          }}>Back to profiles</button>
          <h2>{title || "Untitled profile"}</h2>
          <span className="badge">{selected.size} selected</span>
          <span role="status" className="save-status">{busy ? "Saving…" : saveFailed ? "Save failed" : dirty ? "Unsaved changes" : status ?? (saved ? "All changes saved" : "New profile")}</span>
          {canWrite ? <button type="button" disabled={busy || !data || !title.trim() || selected.size === 0 || unknownIds.length > 0}
            onClick={() => void save()}>{busy ? "Saving…" : "Save profile"}</button> : null}
          {saved && !dirty && !busy ? <a className="button secondary" href={`/bff/tenants/${tenantId}/profiles/${saved.id}/export`}>Export OSCAL JSON</a> : <span className="muted">Save changes before exporting.</span>}
        </div>
        <p className="workspace-source">{catalogName} · {data ? `Pinned revision ${data.revision.revision_number} · OSCAL ${data.revision.oscal_version}` : "Pinned revision"} · <span className="mono">{initialProfile.revision_id}</span></p>
        <div className="workspace-tabs" role="tablist" aria-label="Profile workspace views">
          {VIEWS.map((name, i) => <button key={name} type="button" role="tab" id={`workspace-tab-${i}`}
            aria-selected={view === name} aria-controls={`workspace-view-${i}`} tabIndex={view === name ? 0 : -1}
            onClick={() => setView(name)} onKeyDown={(event) => {
              const next = event.key === "ArrowRight" ? (i + 1) % VIEWS.length
                : event.key === "ArrowLeft" ? (i + VIEWS.length - 1) % VIEWS.length
                  : event.key === "Home" ? 0 : event.key === "End" ? VIEWS.length - 1 : null;
              if (next === null) return;
              event.preventDefault();
              setView(VIEWS[next]);
              document.getElementById(`workspace-tab-${next}`)?.focus();
            }}>{name}{name === "Selected Requirements" ? ` (${selected.size})` : ""}</button>)}
        </div>
        {error ? <p role="alert" className="alert">{error}</p> : null}
      </header>
      {loadError ? <div role="alert" className="alert">{loadError} <button type="button" onClick={() => setLoadAttempt((value) => value + 1)}>Retry catalog loading</button></div> : null}
      {!data && !loadError ? <p role="status">Loading pinned catalog requirements…</p> : null}
      {unknownIds.length > 0 ? <p role="alert" className="alert">These saved IDs are missing from the pinned catalog: {unknownIds.join(", ")}. Saving is disabled; the original selection has been preserved.</p> : null}
      <section role="tabpanel" id="workspace-view-2" aria-labelledby="workspace-tab-2" hidden={view !== "Profile Settings"} className="panel workspace-settings" tabIndex={0}>
        <h2>Profile settings</h2>
        <fieldset className="profile-form" disabled={!canWrite || busy}>
          <label className="field">Profile title
            <input maxLength={255} value={title} onChange={(event) => { setTitle(event.target.value); setStatus(null); }} />
          </label>
          <label className="field">Description or purpose
            <textarea rows={5} maxLength={10000} value={description} onChange={(event) => { setDescription(event.target.value); setStatus(null); }} />
          </label>
        </fieldset>
        <p className="muted">Save profile to apply metadata and selection changes together. The source catalog revision cannot be changed.</p>
      </section>
      <section role="tabpanel" id="workspace-view-1" aria-labelledby="workspace-tab-1" hidden={view !== "Selected Requirements"} className="panel workspace-selection" tabIndex={0}>
        <h2>Selected requirements ({selected.size})</h2>
        <p className="muted">Profile scope only, not implementation or compliance status. Selections reference {catalogName}, pinned revision {data?.revision.revision_number ?? initialProfile.revision_id}.</p>
        <label className="field">Search selected requirements
          <input type="search" value={selectionQuery} placeholder="ID, title or requirement text"
            onChange={(event) => { setSelectionQuery(event.target.value); setSelectionPage(0); }} />
        </label>
        {selectionQuery ? <button type="button" className="secondary" onClick={() => { setSelectionQuery(""); setSelectionPage(0); }}>Clear selection search</button> : null}
        <p role="status">{selectedResults.length} matching selected requirements · {selected.size} total selected</p>
        {!data ? <p>Load the pinned catalog to review selected requirements.</p> : selected.size === 0 ? <p className="empty">Select requirements in the Catalog Browser to define this profile’s scope.</p>
          : selectedResults.length === 0 ? <p className="empty">No selected requirements match this search.</p> : null}
        {selectedGroups.map(([key, group]) => <section key={key} className="selection-group">
          <h3>{group.title}</h3>
          <ul className="result-list">{group.nodes.map((node) => <li key={node.key} className="selection-row">
            <button type="button" onClick={() => navigateTo(node)}><span className="mono">{node.id}</span> {node.title}</button>
            <button type="button" className="secondary" disabled={!canWrite || busy} aria-label={`Remove ${node.id}`} onClick={() => changeSelection([node], false)}>Remove</button>
          </li>)}</ul>
        </section>)}
        {selectionPageCount > 1 ? <nav className="pagination" aria-label="Selected requirement pages">
          <button type="button" className="secondary" disabled={currentSelectionPage === 0} onClick={() => setSelectionPage(currentSelectionPage - 1)}>Previous selected</button>
          <span>Page {currentSelectionPage + 1} of {selectionPageCount}</span>
          <button type="button" className="secondary" disabled={currentSelectionPage >= selectionPageCount - 1} onClick={() => setSelectionPage(currentSelectionPage + 1)}>Next selected</button>
        </nav> : null}
      </section>
      <section role="tabpanel" id="workspace-view-0" aria-labelledby="workspace-tab-0" hidden={view !== "Catalog Browser"} className="workspace-browser" tabIndex={0}>
        <div className="workspace-actions builder-toolbar">
          <button type="button" className="secondary" aria-expanded={showNavigation} aria-controls="catalog-navigation" onClick={() => setShowNavigation(!showNavigation)}>{showNavigation ? "Hide" : "Show"} hierarchy</button>
          <button type="button" className="secondary" aria-expanded={showDetails} aria-controls="requirement-details" onClick={() => setShowDetails(!showDetails)}>{showDetails ? "Hide" : "Show"} details</button>
          <details className="panel-widths"><summary>Panel widths</summary><div>
            <label className="field">Hierarchy width
              <input type="range" min={16} max={24} value={navigationWidth} onChange={(event) => setNavigationWidth(Number(event.target.value))} />
            </label>
            <label className="field">Details width
              <input type="range" min={22} max={36} value={detailWidth} onChange={(event) => setDetailWidth(Number(event.target.value))} />
            </label>
          </div></details>
          <span className="muted">Each checkbox selects one requirement, not its children.</span>
        </div>
      {data ? <div className={`builder-layout${showNavigation ? " has-navigation" : ""}${showDetails ? " has-details" : ""}`}
        style={{ "--navigation-width": `${navigationWidth}rem`, "--detail-width": `${detailWidth}rem` } as CSSProperties}>
        <aside id="catalog-navigation" hidden={!showNavigation} className="panel builder-navigation" aria-label="Catalog navigation">
          <h2>Catalog hierarchy</h2>
          <button type="button" className="secondary" onClick={() => { setBranch(null); setPage(0); }}>All requirements</button>
          {tree(null)}
        </aside>
        <section className="builder-main" aria-label="Requirement browser">
          <div className="panel">
            <label className="field">Search requirements
              <input type="search" value={query} placeholder="ID, title or requirement text"
                onChange={(event) => { setQuery(event.target.value); setPage(0); }} />
            </label>
            <p className="muted">Domain: {branch ? index.byKey.get(branch)?.title : "All domains"}</p>
            <div className="builder-filters">
              {index.facets.slice(0, 2).map(facetField)}
            </div>
            {index.facets.length > 2 ? <details><summary>Advanced filters ({index.facets.slice(2).filter((facet) => filters[facet.key]).length} active)</summary><div className="builder-filters">{index.facets.slice(2).map(facetField)}</div></details> : null}
            <div className="active-filters" aria-label="Active filters">
              {query ? <span className="badge">Search: {query}</span> : null}
              {branch ? <span className="badge">Domain: {index.byKey.get(branch)?.title}</span> : null}
              {index.facets.filter((facet) => filters[facet.key]).map((facet) => <span className="badge" key={facet.key}>{facet.label}: {filters[facet.key]}</span>)}
            </div>
            <button type="button" className="secondary" onClick={() => { setQuery(""); setFilters({}); setBranch(null); setPage(0); }}>Clear search and filters</button>
          </div>
          <div className="panel" id="requirement-results" tabIndex={-1}>
            <h2>Requirements</h2>
            <p role="status">{results.length} matching requirements · {selected.size} selected</p>
            <div className="workspace-actions">
              <button type="button" className="secondary" disabled={!canWrite || busy || !results.length} onClick={() => changeSelection(results, true)}>Select all {results.length} matches</button>
              <button type="button" className="secondary" disabled={!canWrite || busy || !results.length} onClick={() => changeSelection(results, false)}>Deselect matches</button>
            </div>
            {results.length === 0 ? <p className="empty">No requirements match. Clear filters or choose another domain.</p> : null}
            <ul className="requirement-list">
              {visible.map((node) => <li key={node.key} className={node.id && selected.has(node.id) ? "requirement selected" : "requirement"}>
                <label className="requirement-select">
                  <input type="checkbox" disabled={!canWrite || busy} checked={!!node.id && selected.has(node.id)}
                    onChange={(event) => changeSelection([node], event.target.checked)} />
                  <span><span className="mono">{node.id}</span> <strong>{node.title}</strong></span>
                </label>
                <p className="requirement-summary">{renderProse(node.text, PREVIEW_PARAMETERS)}</p>
                <div className="requirement-badges">{node.properties.filter((prop) => ["modal_verb", "sec_level", "effort_level", "tags", "target_object_categories"].includes(prop.name)).map((prop, i) =>
                  <span className="badge" key={i} title={`${prop.name}${prop.ns ? ` (${prop.ns})` : ""}`}>{propertyLabel(prop.name)}: {prop.value}</span>)}</div>
                <div className="workspace-actions">
                  <button type="button" className="secondary" aria-expanded={showDetails && active === node.id} aria-controls="requirement-details" onClick={() => openDetails(node.id)}>Details for {node.id}</button>
                  {(index.children.get(node.key)?.length ?? 0) > 0 ? <>
                    <button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => changeSelection(index.controls.filter((item) => inBranch(item, node.key)), true)}>Select {node.id} and all descendants</button>
                    <button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => changeSelection(index.controls.filter((item) => inBranch(item, node.key)), false)}>Deselect {node.id} and descendants</button>
                  </> : null}
                </div>
              </li>)}
            </ul>
            {pageCount > 1 ? <nav className="pagination" aria-label="Requirement pages">
              <button type="button" className="secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
              <span>Page {currentPage + 1} of {pageCount}</span>
              <button type="button" className="secondary" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>Next</button>
            </nav> : null}
          </div>
        </section>
        <aside hidden={!showDetails} id="requirement-details" tabIndex={-1} className="builder-inspector" aria-label="Requirement details">
          {active ? <RequirementDetails key={`${base}:${active}`} base={base} id={active} /> : <p className="empty">Open requirement details to read the full statement, guidance, properties and parameters.</p>}
        </aside>
      </div> : null}
      </section>
    </div>
  );

  function facetField(facet: ReturnType<typeof indexBrowser>["facets"][number]) {
    return <label className="field" key={facet.key} title={facet.ns}>
      {facet.label}
      <select value={filters[facet.key] ?? ""} onChange={(event) => {
        setFilters((current) => ({ ...current, [facet.key]: event.target.value }));
        setPage(0);
      }}>
        <option value="">All</option>
        {[...facet.values].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((value) => <option key={value} value={value}>{value}</option>)}
      </select>
    </label>;
  }
}

function RequirementDetails({ base, id }: { base: string; id: string }) {
  const [control, setControl] = useState<ControlDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    bffGet<ControlDetail>(`${base}/controls/${encodeURIComponent(id)}`, undefined, controller.signal)
      .then((value) => { if (!controller.signal.aborted) { setControl(value); setError(null); } })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(messageFor(cause)); });
    return () => controller.abort();
  }, [base, id, attempt]);
  if (error) return <p role="alert" className="alert">{error} <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry details</button></p>;
  return control ? <ControlDetailView control={control} presentation="profile" /> : <p role="status">Loading requirement details…</p>;
}

function messageFor(cause: unknown): string {
  return cause instanceof ApiError ? cause.message : ERROR_MESSAGES.unavailable;
}
