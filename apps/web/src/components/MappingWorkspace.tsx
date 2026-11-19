// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import { ApiError } from "@/lib/errors";
import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
import { MappingControlDetails, MappingControlPicker } from "@/components/MappingControlPicker";
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
  ["equal-to", "mappings.equalTo"],
  ["equivalent-to", "mappings.equivalentTo"],
  ["subset-of", "mappings.subsetOf"],
  ["superset-of", "mappings.supersetOf"],
  ["intersects-with", "mappings.intersectsWith"],
  ["no-relationship", "mappings.noRelationship"],
] as const;
const RATIONALES = [
  ["syntactic", "mappings.rationaleSyntactic"],
  ["semantic", "mappings.rationaleSemantic"],
  ["functional", "mappings.rationaleFunctional"],
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
  const { t, number, enumLabel, errorMessage } = useI18n();
  const router = useRouter();
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
  const [draftPairs, setDraftPairs] = useState<Record<string, boolean>>({});
  const [conflict, setConflict] = useState<{ currentVersion: number } | null>(null);
  const [editorEpoch, setEditorEpoch] = useState(0);
  const reportPairDraft = useCallback((clientKey: string, hasDraft: boolean) => {
    setDraftPairs((current) => ({ ...current, [clientKey]: hasDraft }));
  }, []);
  const [baseline, setBaseline] = useState(() => initialCollection
    ? mappingSnapshot(
      initialCollection.title,
      initialCollection.description,
      initialCollection.mappings.map((pair) => initialPair(pair)),
    )
    : mappingSnapshot("", "", [initialPair()]));

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
  const dirty = canWrite && (baseline !== snapshot || Object.values(draftPairs).some(Boolean));
  const valid = title.trim().length > 0 && pairs.length > 0 && pairs.every((pair) =>
    pair.source_catalog_id && pair.source_revision_id && pair.target_catalog_id &&
    pair.target_revision_id && pair.entries.length > 0 &&
    pair.entries.every((entry) => entry.sources.length > 0 && entry.targets.length > 0 &&
      RELATIONSHIPS.some(([value]) => value === entry.relationship) &&
      RATIONALES.some(([value]) => value === entry.matching_rationale)),
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
      if (busy || !window.confirm(t("mappings.discardChanges"))) event.preventDefault();
    };
    const submit = (event: SubmitEvent) => {
      if (busy || !window.confirm(t("mappings.discardChanges"))) event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    document.addEventListener("submit", submit, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", navigate, true);
      document.removeEventListener("submit", submit, true);
    };
  }, [dirty, busy, t]);

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
      setError(errorMessage(cause) || t("mappings.loadMoreCatalogsError"));
    } finally {
      setCatalogLoading(false);
    }
  }

  async function save() {
    if (!valid || busy) return;
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
        collection
          ? { ...body, expected_version: collection.concurrency_version }
          : body,
      );
      setCollection(saved);
      setTitle(saved.title);
      setDescription(saved.description);
      const savedPairs = saved.mappings.map((pair) => initialPair(pair));
      setPairs(savedPairs);
      setBaseline(mappingSnapshot(saved.title, saved.description, savedPairs));
      setStatus(t("mappings.savedNotice"));
      setConflict(null);
      setEditorEpoch((value) => value + 1);
      window.history.replaceState(null, "", `/t/${tenantId}/mappings/${saved.id}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.kind === "stale_update") {
        const detail = cause.detail as { current_version?: number } | undefined;
        setConflict({
          currentVersion: detail?.current_version ?? collection?.concurrency_version ?? 1,
        });
        setError("");
        return;
      }
      setError(errorMessage(cause) || t("mappings.saveError"));
    } finally {
      setBusy(false);
    }
  }

  async function removeCollection() {
    if (!collection || !window.confirm(t("mappings.deleteConfirm", { name: collection.title }))) return;
    setBusy(true);
    setError(null);
    try {
      await bffWrite(
        "DELETE",
        `tenants/${tenantId}/mapping-collections/${collection.id}?expected_version=${collection.concurrency_version}`,
        {},
      );
      router.push(`/t/${tenantId}/mappings`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.kind === "stale_update") {
        const detail = cause.detail as { current_version?: number } | undefined;
        setConflict({
          currentVersion: detail?.current_version ?? collection.concurrency_version,
        });
        setError("");
        setBusy(false);
        return;
      }
      setError(errorMessage(cause) || t("mappings.deleteError"));
      setBusy(false);
    }
  }

  async function reloadAfterConflict() {
    if (!collection || !conflict || busy) return;
    if (!window.confirm(t("mappings.confirmConflictReload"))) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const refreshed = await bffGet<MappingCollection>(
        `tenants/${tenantId}/mapping-collections/${collection.id}`,
      );
      const refreshedPairs = refreshed.mappings.map((pair) => initialPair(pair));
      setCollection(refreshed);
      setTitle(refreshed.title);
      setDescription(refreshed.description);
      setPairs(refreshedPairs);
      setBaseline(mappingSnapshot(refreshed.title, refreshed.description, refreshedPairs));
      setDraftPairs({});
      setConflict(null);
      setEditorEpoch((value) => value + 1);
    } catch (cause) {
      setError(errorMessage(cause) || t("mappings.saveError"));
    } finally {
      setBusy(false);
    }
  }

  return <div className="mapping-workspace">
    <header className="panel mapping-workspace-header">
      <nav className="breadcrumbs" aria-label={t("mappings.breadcrumb")}>
        <a href={`/t/${tenantId}/mappings`}>{t("mappings.navigation")}</a> › <span aria-current="page">{t("mappings.workspace")}</span>
      </nav>
      <div className="mapping-workspace-heading">
        <h1>{t("mappings.workspaceTitle")}</h1>
        {collection ? <span className="badge">OSCAL {collection.oscal_version}</span> : null}
        <span role="status" className="save-status">{busy ? t("mappings.saving") : dirty ? t("mappings.unsavedChanges") : status ?? (collection ? t("mappings.saved") : t("mappings.notSaved"))}</span>
      </div>
      <div className="mapping-workspace-primary">
        <fieldset className="mapping-collection-fields" disabled={!canWrite || busy}>
          <label className="field">{t("mappings.collectionTitle")}
            <input maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)}
              aria-invalid={!title.trim()} />
          </label>
          <label className="field">{t("mappings.description")}
            <textarea maxLength={10000} rows={2} value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
        </fieldset>
        <div className="mapping-primary-actions">
          {collection && !dirty ? <a className="button secondary" href={`/bff/tenants/${tenantId}/mapping-collections/${collection.id}/export`}>{t("mappings.exportJson")}</a> : collection ? <span className="muted">{t("mappings.saveBeforeExport")}</span> : null}
          {canWrite ? <button type="button" disabled={busy || !valid || !dirty} onClick={() => void save()}>{busy ? t("mappings.saving") : collection ? t("mappings.saveChanges") : t("mappings.createCollection")}</button> : null}
        </div>
      </div>
      <p className="mapping-context">{t("mappings.context")}</p>
      {error ? <p role="alert" className="alert">{error}</p> : null}
      {conflict ? <div role="alert" className="panel">
        <p>{t("mappings.conflictDetected", { version: conflict.currentVersion })}</p>
        <p className="muted">{t("mappings.conflictPreserved")}</p>
        <div className="workspace-actions">
          <button type="button" className="danger-action" disabled={busy || !collection}
            onClick={() => void reloadAfterConflict()}>{t("mappings.reloadConfirmedState")}</button>
          <button type="button" className="secondary" disabled={busy}
            onClick={() => setConflict(null)}>{t("mappings.keepMyEdits")}</button>
        </div>
      </div> : null}
      {!valid ? <ul className="muted mapping-validation" aria-label={t("mappings.saveRequirements")}>
        {mappingValidationMessages(title, pairs, t, number).map((message) => <li key={message}>{message}</li>)}
      </ul> : null}
      {canWrite && collection ? <details className="mapping-danger-zone">
        <summary>{t("mappings.collectionSettings")}</summary>
        <p>{t("mappings.deleteCollectionWarning")}</p>
        <button type="button" className="danger-action" disabled={busy} onClick={() => void removeCollection()}>{t("mappings.deleteCollection")}</button>
        <dl className="meta-list mapping-collection-meta">
          <dt>{t("mappings.stableCollectionIdentity")}</dt><dd className="mono">{collection.id}</dd>
          <dt>{t("mappings.oscalDocumentUuid")}</dt><dd className="mono">{collection.oscal_document_uuid}</dd>
          <dt>{t("mappings.version")}</dt><dd>{collection.version}</dd>
        </dl>
      </details> : collection ? <details className="mapping-danger-zone">
        <summary>{t("mappings.technicalDetails")}</summary>
        <dl className="meta-list mapping-collection-meta">
          <dt>{t("mappings.stableCollectionIdentity")}</dt><dd className="mono">{collection.id}</dd>
          <dt>{t("mappings.oscalDocumentUuid")}</dt><dd className="mono">{collection.oscal_document_uuid}</dd>
          <dt>{t("mappings.version")}</dt><dd>{collection.version}</dd>
        </dl>
      </details> : null}
    </header>

    {pairs.map((pair, index) => <MappingPairEditor
      key={`${editorEpoch}:${pair.clientKey}:${pair.source_catalog_id}:${pair.source_revision_id}:${pair.target_catalog_id}:${pair.target_revision_id}`}
      tenantId={tenantId}
      catalogs={catalogOptions}
      allPairs={pairs}
      pair={pair}
      pairNumber={index + 1}
      onDraftChange={(hasDraft) => reportPairDraft(pair.clientKey, hasDraft)}
      canWrite={canWrite && !busy}
      onChange={(updated) => {
        setPairs((current) => current.map((item) => item.clientKey === pair.clientKey ? updated : item));
        if (updated.source_catalog_id !== pair.source_catalog_id ||
            updated.source_revision_id !== pair.source_revision_id ||
            updated.target_catalog_id !== pair.target_catalog_id ||
            updated.target_revision_id !== pair.target_revision_id) {
          reportPairDraft(pair.clientKey, false);
        }
      }}
      onRemove={() => {
        setPairs((current) => current.filter((item) => item.clientKey !== pair.clientKey));
        reportPairDraft(pair.clientKey, false);
      }}
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
    }>{t("mappings.addCatalogPair")}</button> : null}
    {catalogOptions.length < catalogTotal ? <button type="button" className="secondary"
      disabled={catalogLoading} onClick={() => void loadMoreCatalogs()}>
      {catalogLoading ? t("mappings.loadingCatalogs") : t("mappings.loadMoreCatalogs", { count: number(catalogTotal - catalogOptions.length) })}
    </button> : null}
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

function mappingValidationMessages(title: string, pairs: DraftPair[], t: Translate, number: (value: number) => string): string[] {
  const messages: string[] = [];
  if (!title.trim()) messages.push(t("mappings.enterCollectionTitle"));
  if (pairs.length === 0) messages.push(t("mappings.addCatalogPairValidation"));
  pairs.forEach((pair, index) => {
    const side = t("mappings.catalogPair", { number: number(index + 1) });
    if (!pair.source_catalog_id || !pair.source_revision_id || !pair.target_catalog_id || !pair.target_revision_id) {
      messages.push(t("mappings.selectCatalogRevisions", { name: side }));
    }
    if (pair.entries.length === 0) {
      messages.push(t("mappings.addMappingEntryValidation", { name: side }));
    }
    if (pair.entries.some((entry) =>
      entry.sources.length === 0 || entry.targets.length === 0 ||
      !RELATIONSHIPS.some(([value]) => value === entry.relationship) ||
      !RATIONALES.some(([value]) => value === entry.matching_rationale))) {
      messages.push(t("mappings.completeMappingEntry", { name: side }));
    }
  });
  return messages;
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

function mappingControlDisplay(controlId: string, titles: Record<string, string>): string {
  const title = titles[controlId];
  return title ? `${controlId} — ${title}` : controlId;
}

function sameControlSet(
  left: (string | MappingControlReference)[],
  right: (string | MappingControlReference)[],
): boolean {
  const leftIds = left.map(mappingControlId).sort();
  const rightIds = right.map(mappingControlId).sort();
  return leftIds.length === rightIds.length && leftIds.every((id, index) => id === rightIds[index]);
}

function relationshipDescription(relationship: MappingEntryInput["relationship"], t: Translate): string {
  switch (relationship) {
    case "equal-to": return t("mappings.relationshipEqualTo");
    case "equivalent-to": return t("mappings.relationshipEquivalentTo");
    case "subset-of": return t("mappings.relationshipSubsetOf");
    case "superset-of": return t("mappings.relationshipSupersetOf");
    case "intersects-with": return t("mappings.relationshipIntersectsWith");
    case "no-relationship": return t("mappings.relationshipNoRelationship");
  }
}

function MappingPairEditor({
  tenantId, catalogs, allPairs, pair, pairNumber, canWrite, onChange, onRemove, onDraftChange, canRemove,
}: {
  tenantId: string;
  catalogs: Catalog[];
  allPairs: DraftPair[];
  pair: DraftPair;
  pairNumber: number;
  onDraftChange: (hasDraft: boolean) => void;
  canWrite: boolean;
  onChange: (pair: DraftPair) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const { t, number, enumLabel, errorMessage } = useI18n();
  const [sourceControls, setSourceControls] = useState<string[]>([]);
  const [targetControls, setTargetControls] = useState<string[]>([]);
  const [sourceControlTitles, setSourceControlTitles] = useState<Record<string, string>>({});
  const [targetControlTitles, setTargetControlTitles] = useState<Record<string, string>>({});
  const [relationship, setRelationship] = useState<MappingEntryInput["relationship"] | "">("");
  const [rationale, setRationale] = useState<MappingEntryInput["matching_rationale"]>("semantic");
  const [justification, setJustification] = useState("");
  const [editingKey, setEditingKey] = useState<string | undefined>();
  const [pairExpanded, setPairExpanded] = useState(true);
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
        [pair.source_catalog_id]: errorMessage(cause) || t("mappings.loadSourceRevisionsError"),
      })); });
    return () => controller.abort();
  }, [tenantId, pair.source_catalog_id, errorMessage, t]);

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
        [pair.target_catalog_id]: errorMessage(cause) || t("mappings.loadTargetRevisionsError"),
      })); });
    return () => controller.abort();
  }, [tenantId, pair.target_catalog_id, errorMessage, t]);

  function update(patch: Partial<DraftPair>) {
    onChange({ ...pair, ...patch });
  }

  function reportDraft(patch: {
    sourceControls?: string[];
    targetControls?: string[];
    relationship?: MappingEntryInput["relationship"] | "";
    justification?: string;
  }) {
    const sources = patch.sourceControls ?? sourceControls;
    const targets = patch.targetControls ?? targetControls;
    const selectedRelationship = patch.relationship ?? relationship;
    const text = patch.justification ?? justification;
    onDraftChange(Boolean(sources.length || targets.length || selectedRelationship || text.trim() || editingKey));
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
        [catalogId]: errorMessage(cause) || t("mappings.loadMoreRevisionsError"),
      }));
    } finally {
      setLoadingMore(null);
    }
  }

  function beginEdit(entry: DraftEntry) {
    const sources = entry.sources.map(mappingControlId);
    const targets = entry.targets.map(mappingControlId);
    const selectedRelationship = entry.relationship as MappingEntryInput["relationship"];
    setSourceControls(sources);
    setTargetControls(targets);
    setRelationship(selectedRelationship);
    setRationale(entry.matching_rationale as MappingEntryInput["matching_rationale"]);
    setJustification(entry.justification);
    setEditingKey(entry.key);
    onDraftChange(true);
  }

  function addOrUpdateEntry() {
    if (!sourceControls.length || !targetControls.length || !relationship) return;
    const entry: DraftEntry = {
      ...(editingKey ? { id: pair.entries.find((item) => item.key === editingKey)?.id } : {}),
      key: editingKey ?? crypto.randomUUID(),
      sources: sourceControls,
      targets: targetControls,
      relationship,
      matching_rationale: rationale,
      justification: justification.trim(),
    };
    const duplicate = allPairs.some((candidatePair) =>
      candidatePair.source_catalog_id === pair.source_catalog_id &&
      candidatePair.source_revision_id === pair.source_revision_id &&
      candidatePair.target_catalog_id === pair.target_catalog_id &&
      candidatePair.target_revision_id === pair.target_revision_id &&
      candidatePair.entries.some((existing) =>
        !(candidatePair.clientKey === pair.clientKey && existing.key === editingKey) &&
        existing.relationship === entry.relationship &&
        existing.matching_rationale === entry.matching_rationale &&
        existing.justification.trim() === entry.justification &&
        sameControlSet(existing.sources, entry.sources) &&
        sameControlSet(existing.targets, entry.targets)));
    if (duplicate && !window.confirm(t("mappings.duplicateConfirm"))) return;
    const entries = editingKey
      ? pair.entries.map((item) => item.key === editingKey ? entry : item)
      : [...pair.entries, entry];
    update({ entries });
    setSourceControls([]);
    setTargetControls([]);
    setJustification("");
    setEditingKey(undefined);
    setRelationship("");
    onDraftChange(false);
  }

  function cancelEdit() {
    setSourceControls([]);
    setTargetControls([]);
    setJustification("");
    setEditingKey(undefined);
    setRelationship("");
    onDraftChange(false);
  }

  const sourceRevision = sourceRevisions.find((item) => item.id === pair.source_revision_id);
  const targetRevision = targetRevisions.find((item) => item.id === pair.target_revision_id);

  return <details className="mapping-pair" open={pairExpanded}
    onToggle={(event) => setPairExpanded(event.currentTarget.open)}>
    <summary className="mapping-pair-summary">
      <span className="mapping-pair-summary-title">{t("mappings.catalogPair", { number: number(pairNumber) })}</span>
      <span>{sourceCatalog?.name || t("mappings.chooseSource")}{sourceRevision ? ` · ${t("mappings.revisionShort")} ${number(sourceRevision.revision_number)}${sourceRevision.source_version ? ` (v${sourceRevision.source_version})` : ""}` : ""}</span>
      <span aria-hidden="true">→</span>
      <span>{targetCatalog?.name || t("mappings.chooseTarget")}{targetRevision ? ` · ${t("mappings.revisionShort")} ${number(targetRevision.revision_number)}${targetRevision.source_version ? ` (v${targetRevision.source_version})` : ""}` : ""}</span>
      <span className="badge">{number(pair.entries.length)} {t(pair.entries.length === 1 ? "mappings.mappingSingular" : "mappings.mappingPlural")}</span>
    </summary>
    <div className="mapping-pair-content">
      {canRemove ? <div className="workspace-actions mapping-pair-actions">
        <button type="button" className="secondary" disabled={!canWrite} onClick={onRemove}>{t("mappings.pairRemove")}</button>
      </div> : null}
    <div className="mapping-pair-revisions">
      <fieldset disabled={!canWrite || locked}>
        <legend>{t("mappings.sourceRevision")}</legend>
        <label className="field">{t("mappings.catalog")}
          <select value={pair.source_catalog_id} onChange={(event) => update({ source_catalog_id: event.target.value, source_revision_id: "" })}>
            <option value="">{t("mappings.chooseSourceCatalog")}</option>
            {catalogs.map((catalog) => <option key={catalog.id} value={catalog.id}>{catalog.name}</option>)}
          </select>
        </label>
        <RevisionSelect catalogName={sourceCatalog?.name ?? t("mappings.source")} selected={pair.source_revision_id} t={t} number={number} enumLabel={enumLabel}
          revisions={sourceRevisions} onChange={(id) => update({ source_revision_id: id })}
          hasMore={sourceRevisionTotal > sourceRevisions.length} loading={loadingMore === "source"}
          onLoadMore={() => void loadMoreRevisions("source")} />
      </fieldset>
      <fieldset disabled={!canWrite || locked}>
        <legend>{t("mappings.targetRevision")}</legend>
        <label className="field">{t("mappings.catalog")}
          <select value={pair.target_catalog_id} onChange={(event) => update({ target_catalog_id: event.target.value, target_revision_id: "" })}>
            <option value="">{t("mappings.chooseTargetCatalog")}</option>
            {catalogs.map((catalog) => <option key={catalog.id} value={catalog.id}>{catalog.name}</option>)}
          </select>
        </label>
        <RevisionSelect catalogName={targetCatalog?.name ?? t("mappings.target")} selected={pair.target_revision_id} t={t} number={number} enumLabel={enumLabel}
          revisions={targetRevisions} onChange={(id) => update({ target_revision_id: id })}
          hasMore={targetRevisionTotal > targetRevisions.length} loading={loadingMore === "target"}
          onLoadMore={() => void loadMoreRevisions("target")} />
      </fieldset>
    </div>
    {revisionError ? <p role="alert" className="alert">{revisionError}</p> : null}
    {pair.source_catalog_id && pair.source_revision_id && pair.target_catalog_id && pair.target_revision_id ? <>
      <div className="mapping-control-columns">
        <MappingControlPicker tenantId={tenantId} catalogId={pair.source_catalog_id} revisionId={pair.source_revision_id}
          label={`${t("mappings.source")} · ${sourceCatalog?.name ?? t("mappings.catalog")}`} selected={sourceControls}
          onChange={(ids) => { setSourceControls(ids); reportDraft({ sourceControls: ids }); }}
          onControlTitles={setSourceControlTitles} disabled={!canWrite} />
        <MappingControlPicker tenantId={tenantId} catalogId={pair.target_catalog_id} revisionId={pair.target_revision_id}
          label={`${t("mappings.target")} · ${targetCatalog?.name ?? t("mappings.catalog")}`} selected={targetControls}
          onChange={(ids) => { setTargetControls(ids); reportDraft({ targetControls: ids }); }}
          onControlTitles={setTargetControlTitles} disabled={!canWrite} />
      </div>
      <fieldset className="mapping-entry-form" disabled={!canWrite}>
        <legend>{editingKey ? t("mappings.editEntry") : t("mappings.createEntry")}</legend>
        <p className="muted">{t("mappings.assertionScope")}</p>
        <div className="mapping-entry-selection">
          <strong>{t("mappings.selectedSourceSet", { count: number(sourceControls.length) })}</strong>
          <span>{sourceControls.map((id) => mappingControlDisplay(id, sourceControlTitles)).join(", ") || t("mappings.selectSourceControls")}</span>
          <strong>{t("mappings.selectedTargetSet", { count: number(targetControls.length) })}</strong>
          <span>{targetControls.map((id) => mappingControlDisplay(id, targetControlTitles)).join(", ") || t("mappings.selectTargetControls")}</span>
        </div>
        <div className="mapping-pair-revisions">
          <label className="field">{t("mappings.relationship")}
            <select required value={relationship} aria-invalid={!relationship}
              onChange={(event) => {
                const value = event.target.value as MappingEntryInput["relationship"] | "";
                setRelationship(value);
                reportDraft({ relationship: value });
              }}>
              <option value="">{t("mappings.chooseRelationship")}</option>
              {RELATIONSHIPS.map(([value, key]) => <option key={value} value={value}>{t(key)} ({value})</option>)}
            </select>
          </label>
          <label className="field">{t("mappings.matchingRationale")}
            <select value={rationale} onChange={(event) => setRationale(event.target.value as MappingEntryInput["matching_rationale"])}>
              {RATIONALES.map(([value, key]) => <option key={value} value={value}>{t(key)} ({value})</option>)}
            </select>
          </label>
        </div>
        <label className="field">{t("mappings.justification")}
          <textarea rows={3} maxLength={10000} value={justification} onChange={(event) => {
            setJustification(event.target.value);
            reportDraft({ justification: event.target.value });
          }}
            placeholder={t("mappings.justificationPlaceholder")} />
        </label>
        <div className="workspace-actions">
          <button type="button" disabled={!sourceControls.length || !targetControls.length || !relationship}
            onClick={addOrUpdateEntry}>{editingKey ? t("mappings.updateEntry") : t("mappings.addEntry")}</button>
          {editingKey ? <button type="button" className="secondary" onClick={cancelEdit}>{t("mappings.cancelEdit")}</button> : null}
          {relationship ? <span className="mapping-direction" role="status">{relationshipDescription(relationship, t)} ({relationship})</span> : null}
          {!relationship ? <span className="muted">{t("mappings.chooseRelationshipHint")}</span> : null}
        </div>
      </fieldset>
    </> : <p className="muted">{t("mappings.selectRevisionsHint")}</p>}

    <h3>{t("mappings.entriesCount", { count: number(pair.entries.length) })}</h3>
    {pair.entries.length === 0 ? <p className="empty">{t("mappings.noMappings")}</p> : <ul className="mapping-entry-list">
      {pair.entries.map((entry) => <li key={entry.key}>
        <div className="mapping-entry-content">
          <div className="mapping-entry-direction">
            <span className="mapping-entry-set"><strong>{t("mappings.sourceSetCount", { count: number(entry.sources.length) })}</strong>
              {entry.sources.map((value, index) => <span key={`${mappingControlLabel(value)}-${index}`} className="mapping-overview-control">
                <span><span className="mono">{mappingControlId(value)}</span>{sourceControlTitles[mappingControlId(value)] ? ` — ${sourceControlTitles[mappingControlId(value)]}` : ""}</span>
                <MappingControlDetails tenantId={tenantId} catalogId={pair.source_catalog_id}
                  revisionId={pair.source_revision_id} controlId={mappingControlId(value)} />
              </span>)}
            </span>
            <span className="mapping-relation-label">{relationshipDescription(entry.relationship as MappingEntryInput["relationship"], t)} ({entry.relationship})</span>
            <span className="mapping-entry-set"><strong>{t("mappings.targetSetCount", { count: number(entry.targets.length) })}</strong>
              {entry.targets.map((value, index) => <span key={`${mappingControlLabel(value)}-${index}`} className="mapping-overview-control">
                <span><span className="mono">{mappingControlId(value)}</span>{targetControlTitles[mappingControlId(value)] ? ` — ${targetControlTitles[mappingControlId(value)]}` : ""}</span>
                <MappingControlDetails tenantId={tenantId} catalogId={pair.target_catalog_id}
                  revisionId={pair.target_revision_id} controlId={mappingControlId(value)} />
              </span>)}
            </span>
          </div>
          <p><strong>{t("mappings.matchingRationaleLabel")}</strong> {t(entry.matching_rationale === "syntactic" ? "mappings.rationaleSyntactic" : entry.matching_rationale === "functional" ? "mappings.rationaleFunctional" : "mappings.rationaleSemantic")} ({entry.matching_rationale})</p>
          {entry.justification ? <details className="mapping-justification">
            <summary>{t("mappings.justification")}</summary><p>{entry.justification}</p>
          </details> : null}
        </div>
        {canWrite ? <div className="workspace-actions">
          <button type="button" className="secondary" onClick={() => beginEdit(entry)}>{t("mappings.edit")}</button>
          <button type="button" className="secondary" onClick={() => {
            update({ entries: pair.entries.filter((item) => item.key !== entry.key) });
            if (editingKey === entry.key) cancelEdit();
          }}>{t("mappings.remove")}</button>
        </div> : null}
      </li>)}
    </ul>}
    {locked ? <p className="muted">{t("mappings.pinnedLock")}</p> : null}
    <details className="mapping-pair-technical">
      <summary>{t("mappings.technicalRevisionIds")}</summary>
      <dl className="meta-list">
        <dt>{t("mappings.sourceRevisionUuid")}</dt><dd className="mono">{pair.source_revision_id || t("mappings.notSelected")}</dd>
        <dt>{t("mappings.targetRevisionUuid")}</dt><dd className="mono">{pair.target_revision_id || t("mappings.notSelected")}</dd>
      </dl>
    </details>
    </div>
  </details>;
}

function RevisionSelect({
  catalogName, selected, revisions, onChange, hasMore, loading, onLoadMore, t, number, enumLabel,
}: {
  catalogName: string;
  selected: string;
  revisions: RevisionSummary[];
  onChange: (revisionId: string) => void;
  hasMore: boolean;
  loading: boolean;
  onLoadMore: () => void;
  t: Translate;
  number: (value: number) => string;
  enumLabel: (value: string) => string;
}) {
  return <div>
    <label className="field">{t("mappings.revision")}
      <select value={selected} disabled={!revisions.length} onChange={(event) => onChange(event.target.value)}>
        <option value="">{t("mappings.chooseRevision", { name: catalogName })}</option>
        {selected && !revisions.some((item) => item.id === selected)
          ? <option value={selected}>{t("mappings.pinnedUnavailable")}</option> : null}
        {revisions.map((revision) => <option key={revision.id} value={revision.id}>
          {t("mappings.revision", { number: number(revision.revision_number) })}{revision.source_version ? ` (v${revision.source_version})` : ""} · {enumLabel(revision.lifecycle_status)}
        </option>)}
      </select>
    </label>
    {hasMore ? <button type="button" className="secondary" disabled={loading} onClick={onLoadMore}>
      {loading ? t("mappings.loadingRevisions") : t("mappings.loadMoreRevisions")}
    </button> : null}
  </div>;
}
