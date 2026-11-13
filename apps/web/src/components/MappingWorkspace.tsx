"use client";

import { useEffect, useState } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import { MappingControlPicker } from "@/components/MappingControlPicker";
import type {
  Catalog,
  MappingCollection,
  MappingCollectionInput,
  MappingControlReference,
  MappingEntryInput,
  MappingPair,
  MappingPairInput,
  Paged,
  RevisionSummary,
} from "@/lib/types";

const RELATIONSHIPS = [
  ["equal-to", "Equal to"],
  ["equivalent-to", "Equivalent to"],
  ["subset-of", "Subset of"],
  ["superset-of", "Superset of"],
  ["intersects-with", "Intersects with"],
  ["no-relationship", "No relationship"],
] as const;
const RATIONALES = [
  ["syntactic", "Syntactic"],
  ["semantic", "Semantic"],
  ["functional", "Functional"],
] as const;

interface DraftEntry extends MappingEntryInput {
  key: string;
}

interface DraftPair extends Omit<MappingPairInput, "entries"> {
  clientKey: string;
  entries: DraftEntry[];
}

function initialPair(pair?: MappingPair): DraftPair {
  return pair ? {
    id: pair.id,
    clientKey: pair.id,
    source_catalog_id: pair.source_catalog_id,
    source_revision_id: pair.source_revision_id,
    target_catalog_id: pair.target_catalog_id,
    target_revision_id: pair.target_revision_id,
    entries: pair.entries.map((entry) => ({
      ...entry,
      sources: entry.sources.map(mappingControlId),
      targets: entry.targets.map(mappingControlId),
      key: entry.id,
      relationship: entry.relationship as MappingEntryInput["relationship"],
      matching_rationale: entry.matching_rationale as MappingEntryInput["matching_rationale"],
    })),
  } : {
    clientKey: "new-pair",
    source_catalog_id: "",
    source_revision_id: "",
    target_catalog_id: "",
    target_revision_id: "",
    entries: [],
  };
}

export function MappingWorkspace({
  tenantId,
  catalogs,
  catalogTotal,
  canWrite,
  initialCollection,
}: {
  tenantId: string;
  catalogs: Catalog[];
  catalogTotal: number;
  canWrite: boolean;
  initialCollection: MappingCollection | null;
}) {
  const [collection, setCollection] = useState(initialCollection);
  const [title, setTitle] = useState(initialCollection?.title ?? "");
  const [description, setDescription] = useState(initialCollection?.description ?? "");
  const [catalogOptions, setCatalogOptions] = useState(catalogs);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [pairs, setPairs] = useState<DraftPair[]>(() =>
    initialCollection?.mappings.length
      ? initialCollection.mappings.map((pair) => initialPair(pair))
      : [initialPair()],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [baseline, setBaseline] = useState(() => initialCollection
    ? mappingSnapshot(
      initialCollection.title,
      initialCollection.description,
      initialCollection.mappings.map((pair) => initialPair(pair)),
    )
    : null);

  useEffect(() => {
    if (process.env.NODE_ENV !== "development" || !initialCollection) return;
    console.info("[MappingWorkspace] Loaded mapping control references", {
      collectionId: initialCollection.id,
      mappings: initialCollection.mappings.map((pair) => ({
        mappingId: pair.id,
        entries: pair.entries.map((entry) => ({
          entryId: entry.id,
          sourceReferences: entry.sources.map((value) => ({
            inputType: typeof value,
            controlId: mappingControlLabel(value),
          })),
          targetReferences: entry.targets.map((value) => ({
            inputType: typeof value,
            controlId: mappingControlLabel(value),
          })),
        })),
      })),
    });
  }, [initialCollection]);

  const snapshot = mappingSnapshot(title, description, pairs);
  const dirty = canWrite && baseline !== snapshot;
  const valid = title.trim().length > 0 && pairs.length > 0 && pairs.every((pair) =>
    pair.source_catalog_id && pair.source_revision_id && pair.target_catalog_id &&
    pair.target_revision_id && pair.entries.length > 0,
  );

  useEffect(() => {
    if (!dirty && !busy) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (!link || link.getAttribute("href")?.startsWith("#") ||
          link.getAttribute("target") === "_blank" || link.hasAttribute("download") ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      if (busy || !window.confirm("Discard unsaved mapping changes?")) event.preventDefault();
    };
    const submit = (event: SubmitEvent) => {
      if (busy || !window.confirm("Discard unsaved mapping changes?")) event.preventDefault();
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

  async function loadMoreCatalogs() {
    setCatalogLoading(true);
    setError(null);
    try {
      const result = await bffGet<Paged<Catalog>>(`tenants/${tenantId}/catalogs`, {
        limit: 200,
        offset: catalogOptions.length,
      });
      setCatalogOptions((current) => [...current, ...result.items]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load additional catalogs.");
    } finally {
      setCatalogLoading(false);
    }
  }

  async function save() {
    if (!valid) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    const body: MappingCollectionInput = {
      title: title.trim(),
      description,
      mappings: pairs.map(({ clientKey: _clientKey, ...pair }) => ({
        ...pair,
        entries: pair.entries.map(({ key: _key, ...entry }) => entry),
      })),
    };
    try {
      const saved = await bffWrite<MappingCollection>(
        collection ? "PUT" : "POST",
        collection
          ? `tenants/${tenantId}/mapping-collections/${collection.id}`
          : `tenants/${tenantId}/mapping-collections`,
        body,
      );
      setCollection(saved);
      setTitle(saved.title);
      setDescription(saved.description);
      const savedPairs = saved.mappings.map((pair) => initialPair(pair));
      setPairs(savedPairs);
      setBaseline(mappingSnapshot(saved.title, saved.description, savedPairs));
      setStatus("Mapping collection saved.");
      window.history.replaceState(null, "", `/t/${tenantId}/mappings/${saved.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save this mapping collection.");
    } finally {
      setBusy(false);
    }
  }

  async function removeCollection() {
    if (!collection || !window.confirm(`Delete “${collection.title}” and its mappings?`)) return;
    setBusy(true);
    setError(null);
    try {
      await bffWrite("DELETE", `tenants/${tenantId}/mapping-collections/${collection.id}`, {});
      window.location.assign(`/t/${tenantId}/mappings`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete this mapping collection.");
      setBusy(false);
    }
  }

  return <div className="mapping-workspace">
    <header className="panel">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <a href={`/t/${tenantId}/mappings`}>Control mappings</a>
        {collection ? <> › <span aria-current="page">{collection.title}</span></> : <> › <span aria-current="page">New collection</span></>}
      </nav>
      <div className="workspace-actions">
        <h2>{collection ? "Mapping collection" : "Create mapping collection"}</h2>
        {collection ? <span className="badge">OSCAL {collection.oscal_version}</span> : null}
        <span role="status" className="save-status">{busy ? "Saving…" : dirty ? "Unsaved changes" : status ?? (collection ? "Saved" : "Not saved")}</span>
        {collection && !dirty ? <a className="button secondary" href={`/bff/tenants/${tenantId}/mapping-collections/${collection.id}/export`}>Export OSCAL JSON</a> : collection ? <span className="muted">Save changes before exporting.</span> : null}
        {canWrite ? <button type="button" disabled={busy || !valid || !dirty} onClick={() => void save()}>{busy ? "Saving…" : collection ? "Save changes" : "Create collection"}</button> : null}
        {canWrite && collection ? <button type="button" className="secondary" disabled={busy} onClick={() => void removeCollection()}>Delete collection</button> : null}
      </div>
      <fieldset className="mapping-collection-fields" disabled={!canWrite || busy}>
        <label className="field">Collection title
          <input maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
        </label>
        <label className="field">Description
          <textarea maxLength={10000} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
      </fieldset>
      <p className="muted">Mappings describe relationships between pinned normative controls. They do not select Profile controls or indicate implementation or compliance status.</p>
      <p className="muted">Mapping method is human (manual authoring) and status is draft. Matching rationale describes why controls are related, not how this mapping was produced.</p>
      {error ? <p role="alert" className="alert">{error}</p> : null}
    </header>

    {pairs.map((pair, index) => <MappingPairEditor
      key={`${pair.clientKey}:${pair.source_catalog_id}:${pair.source_revision_id}:${pair.target_catalog_id}:${pair.target_revision_id}`}
      tenantId={tenantId}
      catalogs={catalogOptions}
      pair={pair}
      pairNumber={index + 1}
      canWrite={canWrite && !busy}
      onChange={(updated) => setPairs((current) => current.map((item) => item.clientKey === pair.clientKey ? updated : item))}
      onRemove={() => setPairs((current) => current.filter((item) => item.clientKey !== pair.clientKey))}
      canRemove={pairs.length > 1}
    />)}
    {canWrite ? <button type="button" className="secondary" disabled={busy} onClick={() =>
      setPairs((current) => [...current, {
        clientKey: crypto.randomUUID(),
        source_catalog_id: "",
        source_revision_id: "",
        target_catalog_id: "",
        target_revision_id: "",
        entries: [],
      }])
    }>Add catalog pair</button> : null}
    {catalogOptions.length < catalogTotal ? <button type="button" className="secondary"
      disabled={catalogLoading} onClick={() => void loadMoreCatalogs()}>
      {catalogLoading ? "Loading catalogs…" : `Load more catalogs (${catalogTotal - catalogOptions.length} remaining)`}
    </button> : null}
    {!valid ? <p className="muted">Choose source and target catalog revisions and add at least one mapping entry to each pair before saving.</p> : null}
    {collection ? <dl className="meta-list mapping-collection-meta">
      <dt>Stable collection identity</dt><dd className="mono">{collection.id}</dd>
      <dt>OSCAL document UUID</dt><dd className="mono">{collection.oscal_document_uuid}</dd>
      <dt>Version</dt><dd>{collection.version}</dd>
    </dl> : null}
  </div>;
}

function mappingSnapshot(title: string, description: string, pairs: DraftPair[]): string {
  return JSON.stringify({
    title: title.trim(),
    description,
    mappings: pairs.map(({ clientKey: _clientKey, ...pair }) => ({
      ...pair,
      entries: pair.entries.map(({ key: _key, ...entry }) => entry),
    })),
  });
}

function mappingControlId(value: string | MappingControlReference): string {
  if (typeof value === "string") return value;
  if ("id-ref" in value) return value["id-ref"];
  if ("id_ref" in value) return value.id_ref;
  return value.control_id;
}

function mappingControlLabel(value: string | MappingControlReference): string {
  const controlId = mappingControlId(value);
  if (controlId) return controlId;
  return JSON.stringify(value);
}

function MappingPairEditor({
  tenantId, catalogs, pair, pairNumber, canWrite, onChange, onRemove, canRemove,
}: {
  tenantId: string;
  catalogs: Catalog[];
  pair: DraftPair;
  pairNumber: number;
  canWrite: boolean;
  onChange: (pair: DraftPair) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const [sourceControls, setSourceControls] = useState<string[]>([]);
  const [targetControls, setTargetControls] = useState<string[]>([]);
  const [relationship, setRelationship] = useState<MappingEntryInput["relationship"]>("equivalent-to");
  const [rationale, setRationale] = useState<MappingEntryInput["matching_rationale"]>("semantic");
  const [justification, setJustification] = useState("");
  const [editingKey, setEditingKey] = useState<string | undefined>();
  const [sourceRevisionData, setSourceRevisionData] = useState<{ catalogId: string; items: RevisionSummary[]; total: number } | null>(null);
  const [targetRevisionData, setTargetRevisionData] = useState<{ catalogId: string; items: RevisionSummary[]; total: number } | null>(null);
  const [revisionErrors, setRevisionErrors] = useState<Record<string, string>>({});
  const [loadingMore, setLoadingMore] = useState<"source" | "target" | null>(null);
  const locked = pair.entries.length > 0;
  const sourceRevisions = sourceRevisionData?.catalogId === pair.source_catalog_id ? sourceRevisionData.items : [];
  const targetRevisions = targetRevisionData?.catalogId === pair.target_catalog_id ? targetRevisionData.items : [];
  const sourceRevisionTotal = sourceRevisionData?.catalogId === pair.source_catalog_id ? sourceRevisionData.total : 0;
  const targetRevisionTotal = targetRevisionData?.catalogId === pair.target_catalog_id ? targetRevisionData.total : 0;
  const revisionError = revisionErrors[pair.source_catalog_id] ?? revisionErrors[pair.target_catalog_id] ?? null;
  const sourceCatalog = catalogs.find((catalog) => catalog.id === pair.source_catalog_id);
  const targetCatalog = catalogs.find((catalog) => catalog.id === pair.target_catalog_id);

  useEffect(() => {
    if (!pair.source_catalog_id) return;
    const controller = new AbortController();
    bffGet<Paged<RevisionSummary>>(`tenants/${tenantId}/catalogs/${pair.source_catalog_id}/revisions`, { limit: 200, offset: 0 }, controller.signal)
      .then((result) => {
        setSourceRevisionData({ catalogId: pair.source_catalog_id, items: result.items, total: result.total });
        setRevisionErrors((current) => {
          const next = { ...current };
          delete next[pair.source_catalog_id];
          return next;
        });
      })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setRevisionErrors((current) => ({
        ...current,
        [pair.source_catalog_id]: cause instanceof Error ? cause.message : "Unable to load source revisions.",
      })); });
    return () => controller.abort();
  }, [tenantId, pair.source_catalog_id]);

  useEffect(() => {
    if (!pair.target_catalog_id) return;
    const controller = new AbortController();
    bffGet<Paged<RevisionSummary>>(`tenants/${tenantId}/catalogs/${pair.target_catalog_id}/revisions`, { limit: 200, offset: 0 }, controller.signal)
      .then((result) => {
        setTargetRevisionData({ catalogId: pair.target_catalog_id, items: result.items, total: result.total });
        setRevisionErrors((current) => {
          const next = { ...current };
          delete next[pair.target_catalog_id];
          return next;
        });
      })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setRevisionErrors((current) => ({
        ...current,
        [pair.target_catalog_id]: cause instanceof Error ? cause.message : "Unable to load target revisions.",
      })); });
    return () => controller.abort();
  }, [tenantId, pair.target_catalog_id]);

  function update(patch: Partial<DraftPair>) {
    onChange({ ...pair, ...patch });
  }

  async function loadMoreRevisions(side: "source" | "target") {
    const catalogId = side === "source" ? pair.source_catalog_id : pair.target_catalog_id;
    const current = side === "source" ? sourceRevisionData : targetRevisionData;
    if (!catalogId || !current || loadingMore) return;
    setLoadingMore(side);
    try {
      const page = await bffGet<Paged<RevisionSummary>>(
        `tenants/${tenantId}/catalogs/${catalogId}/revisions`,
        { limit: 200, offset: current.items.length },
      );
      if (side === "source") {
        setSourceRevisionData((value) => value?.catalogId === catalogId
          ? { ...value, items: [...value.items, ...page.items], total: page.total }
          : value);
      } else {
        setTargetRevisionData((value) => value?.catalogId === catalogId
          ? { ...value, items: [...value.items, ...page.items], total: page.total }
          : value);
      }
    } catch (cause) {
      setRevisionErrors((currentErrors) => ({
        ...currentErrors,
        [catalogId]: cause instanceof Error ? cause.message : "Unable to load additional catalog revisions.",
      }));
    } finally {
      setLoadingMore(null);
    }
  }

  function beginEdit(entry: DraftEntry) {
    setSourceControls(entry.sources.map(mappingControlId));
    setTargetControls(entry.targets.map(mappingControlId));
    setRelationship(entry.relationship as MappingEntryInput["relationship"]);
    setRationale(entry.matching_rationale as MappingEntryInput["matching_rationale"]);
    setJustification(entry.justification);
    setEditingKey(entry.key);
  }

  function addOrUpdateEntry() {
    if (!sourceControls.length || !targetControls.length) return;
    const entry: DraftEntry = {
      ...(editingKey ? { id: pair.entries.find((item) => item.key === editingKey)?.id } : {}),
      key: editingKey ?? crypto.randomUUID(),
      sources: sourceControls,
      targets: targetControls,
      relationship,
      matching_rationale: rationale,
      justification: justification.trim(),
    };
    const entries = editingKey
      ? pair.entries.map((item) => item.key === editingKey ? entry : item)
      : [...pair.entries, entry];
    update({ entries });
    setSourceControls([]);
    setTargetControls([]);
    setJustification("");
    setEditingKey(undefined);
  }

  function cancelEdit() {
    setSourceControls([]);
    setTargetControls([]);
    setJustification("");
    setEditingKey(undefined);
  }

  return <section className="panel mapping-pair" aria-labelledby={`mapping-pair-${pairNumber}`}>
    <div className="workspace-actions">
      <h2 id={`mapping-pair-${pairNumber}`}>Catalog pair {pairNumber}</h2>
      {canRemove ? <button type="button" className="secondary" disabled={!canWrite} onClick={onRemove}>Remove pair</button> : null}
    </div>
    <div className="mapping-pair-revisions">
      <fieldset disabled={!canWrite || locked}>
        <legend>Source catalog revision</legend>
        <label className="field">Catalog
          <select value={pair.source_catalog_id} onChange={(event) => update({ source_catalog_id: event.target.value, source_revision_id: "" })}>
            <option value="">Choose source catalog</option>
            {catalogs.map((catalog) => <option key={catalog.id} value={catalog.id}>{catalog.name}</option>)}
          </select>
        </label>
        <RevisionSelect catalogName={sourceCatalog?.name ?? "source"} selected={pair.source_revision_id}
          revisions={sourceRevisions} onChange={(id) => update({ source_revision_id: id })}
          hasMore={sourceRevisionTotal > sourceRevisions.length} loading={loadingMore === "source"}
          onLoadMore={() => void loadMoreRevisions("source")} />
      </fieldset>
      <fieldset disabled={!canWrite || locked}>
        <legend>Target catalog revision</legend>
        <label className="field">Catalog
          <select value={pair.target_catalog_id} onChange={(event) => update({ target_catalog_id: event.target.value, target_revision_id: "" })}>
            <option value="">Choose target catalog</option>
            {catalogs.map((catalog) => <option key={catalog.id} value={catalog.id}>{catalog.name}</option>)}
          </select>
        </label>
        <RevisionSelect catalogName={targetCatalog?.name ?? "target"} selected={pair.target_revision_id}
          revisions={targetRevisions} onChange={(id) => update({ target_revision_id: id })}
          hasMore={targetRevisionTotal > targetRevisions.length} loading={loadingMore === "target"}
          onLoadMore={() => void loadMoreRevisions("target")} />
      </fieldset>
    </div>
    {revisionError ? <p role="alert" className="alert">{revisionError}</p> : null}
    {pair.source_catalog_id && pair.source_revision_id && pair.target_catalog_id && pair.target_revision_id ? <>
      <div className="mapping-control-columns">
        <MappingControlPicker tenantId={tenantId} catalogId={pair.source_catalog_id} revisionId={pair.source_revision_id}
          label={`Source · ${sourceCatalog?.name ?? "catalog"}`} selected={sourceControls}
          onChange={setSourceControls} disabled={!canWrite} />
        <MappingControlPicker tenantId={tenantId} catalogId={pair.target_catalog_id} revisionId={pair.target_revision_id}
          label={`Target · ${targetCatalog?.name ?? "catalog"}`} selected={targetControls}
          onChange={setTargetControls} disabled={!canWrite} />
      </div>
      <fieldset className="mapping-entry-form" disabled={!canWrite}>
        <legend>{editingKey ? "Edit mapping entry" : "New mapping entry"}</legend>
        <div className="mapping-pair-revisions">
          <label className="field">Relationship
            <select value={relationship} onChange={(event) => setRelationship(event.target.value as MappingEntryInput["relationship"])}>
              {RELATIONSHIPS.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
            </select>
          </label>
          <label className="field">Matching rationale
            <select value={rationale} onChange={(event) => setRationale(event.target.value as MappingEntryInput["matching_rationale"])}>
              {RATIONALES.map(([value, name]) => <option key={value} value={value}>{name}</option>)}
            </select>
          </label>
        </div>
        <label className="field">Justification
          <textarea rows={3} maxLength={10000} value={justification} onChange={(event) => setJustification(event.target.value)}
            placeholder="Describe the basis for this relationship." />
        </label>
        <div className="workspace-actions">
          <button type="button" disabled={!sourceControls.length || !targetControls.length}
            onClick={addOrUpdateEntry}>{editingKey ? "Update mapping entry" : "Add mapping entry"}</button>
          {editingKey ? <button type="button" className="secondary" onClick={cancelEdit}>Cancel edit</button> : null}
          <span className="muted">The relationship applies to each selected set as a whole; no pairwise or transitive mappings are inferred.</span>
        </div>
      </fieldset>
    </> : <p className="muted">Select a source and target catalog revision to browse controls.</p>}

    <h3>Mappings in this catalog pair ({pair.entries.length})</h3>
    {pair.entries.length === 0 ? <p className="empty">No mappings added yet.</p> : <ul className="mapping-entry-list">
      {pair.entries.map((entry) => <li key={entry.key}>
        <div><strong>{entry.relationship}</strong> · {entry.matching_rationale}
          <p>Source set: {entry.sources.map((value, index) => <span className="mono" key={`${mappingControlLabel(value)}-${index}`}>
            {mappingControlLabel(value)}{index < entry.sources.length - 1 ? ", " : ""}
          </span>)}</p>
          <p>Target set: {entry.targets.map((value, index) => <span className="mono" key={`${mappingControlLabel(value)}-${index}`}>
            {mappingControlLabel(value)}{index < entry.targets.length - 1 ? ", " : ""}
          </span>)}</p>
          {entry.justification ? <p>{entry.justification}</p> : null}
        </div>
        {canWrite ? <div className="workspace-actions">
          <button type="button" className="secondary" onClick={() => beginEdit(entry)}>Edit</button>
          <button type="button" className="secondary" onClick={() => {
            update({ entries: pair.entries.filter((item) => item.key !== entry.key) });
            if (editingKey === entry.key) cancelEdit();
          }}>Remove</button>
        </div> : null}
      </li>)}
    </ul>}
    {locked ? <p className="muted">Pinned revisions cannot be changed while this pair contains entries. Remove all entries first to choose different revisions.</p> : null}
  </section>;
}

function RevisionSelect({
  catalogName, selected, revisions, onChange, hasMore, loading, onLoadMore,
}: {
  catalogName: string;
  selected: string;
  revisions: RevisionSummary[];
  onChange: (revisionId: string) => void;
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
}) {
  return <div>
    <label className="field">Revision
      <select value={selected} disabled={!revisions.length} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose {catalogName} revision</option>
        {selected && !revisions.some((item) => item.id === selected)
          ? <option value={selected}>{selected}</option> : null}
        {revisions.map((revision) => <option key={revision.id} value={revision.id}>
          Revision {revision.revision_number} · {revision.id}
        </option>)}
      </select>
    </label>
    {hasMore ? <button type="button" className="secondary" disabled={loading} onClick={onLoadMore}>
      {loading ? "Loading revisions…" : "Load more revisions"}
    </button> : null}
  </div>;
}
