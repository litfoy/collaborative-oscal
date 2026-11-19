// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { COMPONENT_TYPES, componentTypeLabel } from "@/components/ComponentDefinitionWorkspace";
import { MappingControlDetails } from "@/components/MappingControlPicker";
import { MeasureRequirementPicker } from "@/components/MeasureRequirementPicker";
import { bffGet, bffWrite } from "@/lib/bff-client";
import { ApiError } from "@/lib/errors";
import { useI18n } from "@/lib/i18n/provider";
import type {
  Catalog, ComponentDefinition, ComponentDefinitionInput, ComponentRequirementInput, ProfileBrowserNode,
  RelatedMapping, ReusableComponentInput, RevisionDetail,
} from "@/lib/types";

type DraftComponent = ReusableComponentInput & { clientId: string };
const TABS = ["Overview", "Requirements", "OSCAL Details"] as const;
type Tab = typeof TABS[number];

function draftComponents(document: ComponentDefinition): DraftComponent[] {
  return document.components.map((component) => ({
    id: component.id, clientId: component.id, type: component.type, title: component.title,
    description: component.description, requirements: component.requirements.map((requirement) => ({ ...requirement })),
  }));
}

function snapshot(title: string, components: DraftComponent[]) {
  return JSON.stringify({ title, components });
}

export function MeasureDetailWorkspace({
  tenantId, initialDocument, componentId, catalogs, catalogTotal, canWrite,
}: {
  tenantId: string;
  initialDocument: ComponentDefinition;
  componentId: string;
  catalogs: Catalog[];
  catalogTotal: number;
  canWrite: boolean;
}) {
  const { t, number, date, errorMessage } = useI18n();
  const router = useRouter();
  const [document, setDocument] = useState(initialDocument);
  const [documentTitle, setDocumentTitle] = useState(initialDocument.title);
  const [components, setComponents] = useState(() => draftComponents(initialDocument));
  const [activeId, setActiveId] = useState(componentId);
  const [baseline, setBaseline] = useState(() => snapshot(initialDocument.title, draftComponents(initialDocument)));
  const [tab, setTab] = useState<Tab>("Overview");
  const [picker, setPicker] = useState(false);
  const [pickerPending, setPickerPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [conflict, setConflict] = useState<{ currentVersion: number } | null>(null);
  const component = components.find((item) => item.clientId === activeId);
  const savedComponent = document.components.find((item) => item.id === component?.id);
  const dirty = snapshot(documentTitle, components) !== baseline;
  const valid = Boolean(documentTitle.trim() && components.length && components.every((item) =>
    item.title.trim() && item.type.trim() && item.requirements.length <= 1000 &&
      item.requirements.every((requirement) => requirement.description.trim()),
  ) && components.length <= 1000);
  const groups = useMemo(() => {
    const result = new Map<string, ComponentRequirementInput[]>();
    for (const requirement of component?.requirements ?? []) {
      const key = `${requirement.catalog_id}:${requirement.revision_id}`;
      result.set(key, [...(result.get(key) ?? []), requirement]);
    }
    return [...result.entries()];
  }, [component?.requirements]);

  useEffect(() => {
    if (!dirty && !pickerPending && !busy) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (!link || link.getAttribute("href")?.startsWith("#") || link.getAttribute("target") === "_blank" ||
          link.hasAttribute("download") || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      if (busy || !window.confirm(t("measures.discardChanges"))) event.preventDefault();
    };
    const submit = (event: SubmitEvent) => {
      if (busy || !window.confirm(t("measures.discardChanges"))) event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    window.document.addEventListener("click", navigate, true);
    window.document.addEventListener("submit", submit, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      window.document.removeEventListener("click", navigate, true);
      window.document.removeEventListener("submit", submit, true);
    };
  }, [dirty, pickerPending, busy, t]);

  function update(patch: Partial<DraftComponent>) {
    setComponents((current) => current.map((item) => item.clientId === activeId ? { ...item, ...patch } : item));
    setStatus(null);
  }

  function applySavedDocument(saved: ComponentDefinition, nextActiveId?: string) {
    const savedComponents = draftComponents(saved);
    const resolvedActive = nextActiveId && savedComponents.some((item) => item.clientId === nextActiveId)
      ? nextActiveId
      : savedComponents[0]?.clientId ?? "";
    setDocument(saved);
    setDocumentTitle(saved.title);
    setComponents(savedComponents);
    setBaseline(snapshot(saved.title, savedComponents));
    setActiveId(resolvedActive);
    if (resolvedActive) {
      window.history.replaceState(null, "", `/t/${tenantId}/measures/${saved.id}/${resolvedActive}`);
    }
  }

  async function save() {
    if (!canWrite || !dirty || !valid || busy || picker) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    const body: ComponentDefinitionInput = {
      expected_version: document.concurrency_version,
      title: documentTitle.trim(),
      components: components.map(({ clientId: _clientId, ...item }) => item),
    };
    try {
      const saved = await bffWrite<ComponentDefinition>("PUT", `tenants/${tenantId}/component-definitions/${document.id}`, body);
      const activeIndex = components.findIndex((item) => item.clientId === activeId);
      const savedActive = saved.components.find((item) => item.id === component?.id) ?? saved.components[activeIndex];
      applySavedDocument(saved, savedActive?.id);
      setConflict(null);
      setStatus(t("measures.saved"));
    } catch (cause) {
      if (cause instanceof ApiError && cause.kind === "stale_update") {
        const detail = cause.detail as { current_version?: number } | undefined;
        setConflict({ currentVersion: detail?.current_version ?? document.concurrency_version });
        setError("");
        return;
      }
      setError(errorMessage(cause) || t("measures.saveError"));
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument() {
    if (!canWrite || busy || !window.confirm(t(document.components.length === 1 ? "measures.documentDeleteConfirmOne" : "measures.documentDeleteConfirmOther", {
      name: document.title, count: number(document.components.length), extra: dirty ? t("measures.unsavedLostInfo") : "",
    }))) return;
    setBusy(true);
    setError(null);
    try {
      await bffWrite(
        "DELETE",
        `tenants/${tenantId}/component-definitions/${document.id}?expected_version=${document.concurrency_version}`,
        {},
      );
      router.push(`/t/${tenantId}/measures`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.kind === "stale_update") {
        const detail = cause.detail as { current_version?: number } | undefined;
        setConflict({ currentVersion: detail?.current_version ?? document.concurrency_version });
        setError("");
        setBusy(false);
        return;
      }
      setError(errorMessage(cause) || t("measures.deleteDocumentError"));
      setBusy(false);
    }
  }

  async function removeComponent() {
    if (!component || !canWrite || busy) return;
    if (!component.id) {
      if (!window.confirm(t("measures.componentDraftDeleteConfirm", { name: component.title || t("measures.newComponent") }))) return;
      setComponents((current) => current.filter((item) => item.clientId !== activeId));
      setActiveId(components.find((item) => item.clientId !== activeId)?.clientId ?? "");
      return;
    }
    if (!window.confirm(t("measures.componentDeleteConfirm", {
      name: component.title,
      extra: `${document.components.length === 1 ? t("measures.lastComponentDeleteInfo") : ""}${dirty ? t("measures.unsavedDocumentLostInfo") : ""}`,
    }))) return;
    setBusy(true);
    setError(null);
    try {
      const removed = await bffWrite<ComponentDefinition>(
        "DELETE",
        `tenants/${tenantId}/component-definitions/${document.id}/components/${component.id}?expected_version=${document.concurrency_version}`,
        {},
      );
      if (!removed) {
        router.push(`/t/${tenantId}/measures`);
        return;
      }
      const nextActive = removed.components.find((item) => item.id !== component.id)?.id;
      applySavedDocument(removed, nextActive);
      setConflict(null);
      setStatus(t("measures.saved"));
      setBusy(false);
    } catch (cause) {
      if (cause instanceof ApiError && cause.kind === "stale_update") {
        const detail = cause.detail as { current_version?: number } | undefined;
        setConflict({ currentVersion: detail?.current_version ?? document.concurrency_version });
        setError("");
        setBusy(false);
        return;
      }
      setError(errorMessage(cause) || t("measures.deleteComponentError"));
      setBusy(false);
    }
  }

  async function reloadAfterConflict() {
    if (!conflict || busy || picker || pickerPending) return;
    if (!window.confirm(t("measures.confirmConflictReload"))) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const refreshed = await bffGet<ComponentDefinition>(`tenants/${tenantId}/component-definitions/${document.id}`);
      const preserved = refreshed.components.find((item) => item.id === component?.id)?.id;
      applySavedDocument(refreshed, preserved);
      setConflict(null);
    } catch (cause) {
      setError(errorMessage(cause) || t("measures.saveError"));
    } finally {
      setBusy(false);
    }
  }

  function closePicker() {
    if (pickerPending && !window.confirm(t("measures.discardRequirementsConfirm"))) return;
    setPicker(false);
    setPickerPending(false);
  }

  if (!component) return <div className="measure-workspace">
    <p role="alert" className="alert">{t("measures.componentNotFound")}</p>
    <a href={`/t/${tenantId}/measures`}>{t("measures.returnToLibrary")}</a>
  </div>;

  return <div className="measure-workspace">
    <header className="panel mapping-workspace-header">
      <nav className="breadcrumbs" aria-label={t("measures.breadcrumb")}><a href={`/t/${tenantId}/measures`}>{t("measures.library")}</a> › <span aria-current="page">{component.title || t("measures.newComponent")}</span></nav>
      <div className="workspace-actions measure-heading">
        <div><h1>{component.title || t("measures.newComponent")}</h1><span className="muted">{componentTypeLabel(component.type, t)}</span></div>
        <span role="status">{busy ? t("measures.working") : dirty || pickerPending ? t("measures.unsavedChanges") : status ?? t("measures.saved")}</span>
        {canWrite ? <button type="button" disabled={!dirty || !valid || busy || picker} onClick={() => void save()}>{t("measures.saveChanges")}</button> : null}
        {!dirty && !pickerPending && !busy ? <a className="button secondary" href={`/bff/tenants/${tenantId}/component-definitions/${document.id}/export`}>{t("measures.exportJson")}</a>
          : <span className="muted">{t("measures.saveBeforeExport")}</span>}
      </div>
      {!valid && dirty ? <p role="alert" className="alert">{t("measures.documentValidation")}</p> : null}
      {components.some((item) => item.requirements.length > 1000) || components.length > 1000
        ? <p role="alert" className="alert">{t("measures.limitValidation")}</p> : null}
      {error ? <p role="alert" className="alert">{error}</p> : null}
      {conflict ? <div role="alert" className="panel">
        <p>{t("measures.conflictDetected", { version: conflict.currentVersion })}</p>
        <p className="muted">{t("measures.conflictPreserved")}</p>
        <div className="workspace-actions">
          <button type="button" className="danger-action" disabled={busy || picker || pickerPending}
            onClick={() => void reloadAfterConflict()}>{t("measures.reloadConfirmedState")}</button>
          <button type="button" className="secondary" disabled={busy}
            onClick={() => setConflict(null)}>{t("measures.keepMyEdits")}</button>
        </div>
      </div> : null}
      {!picker ? <div className="workspace-tabs" role="tablist" aria-label={t("measures.workspaceViews")}>
        {TABS.map((name, index) => <button key={name} type="button" role="tab" id={`measure-tab-${index}`}
          aria-selected={tab === name} aria-controls={`measure-panel-${index}`} tabIndex={tab === name ? 0 : -1}
          onClick={() => setTab(name)} onKeyDown={(event) => {
            const next = event.key === "ArrowRight" ? (index + 1) % TABS.length : event.key === "ArrowLeft" ? (index + TABS.length - 1) % TABS.length
              : event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : null;
            if (next === null) return;
            event.preventDefault(); setTab(TABS[next]); window.document.getElementById(`measure-tab-${next}`)?.focus();
          }}>{t(name === "Overview" ? "measures.overview" : name === "Requirements" ? "measures.requirements" : "measures.oscalDetails")}{name === "Requirements" ? ` (${number(component.requirements.length)})` : ""}</button>)}
      </div> : null}
    </header>
    {picker ? <MeasureRequirementPicker tenantId={tenantId} catalogs={catalogs} catalogTotal={catalogTotal}
      existing={component.requirements} onPendingChange={setPickerPending} onCancel={closePicker}
      onConfirm={(items) => {
        const existing = new Set(component.requirements.map((item) => `${item.catalog_id}:${item.revision_id}:${item.control_id}`));
        update({ requirements: [...component.requirements, ...items.filter((item) => !existing.has(`${item.catalog_id}:${item.revision_id}:${item.control_id}`))] });
        setPicker(false); setPickerPending(false); setTab("Requirements");
      }} /> : <>
      <section role="tabpanel" id="measure-panel-0" aria-labelledby="measure-tab-0" hidden={tab !== "Overview"} className="panel" tabIndex={0}>
        <h2>{t("measures.overview")}</h2>
        <fieldset className="profile-form measure-form" disabled={!canWrite || busy}>
          <label className="field">{t("measures.title")}<input required maxLength={255} value={component.title} onChange={(event) => update({ title: event.target.value })} /></label>
          <label className="field">{t("measures.componentType")}<select value={component.type} onChange={(event) => update({ type: event.target.value })}>
            {COMPONENT_TYPES.map(([value, key]) => <option key={value} value={value}>{t(key)}</option>)}
            {!COMPONENT_TYPES.some(([value]) => value === component.type) ? <option value={component.type}>{component.type}</option> : null}
          </select></label>
          <label className="field">{t("measures.reusableDescription")}<textarea maxLength={50000} rows={6} value={component.description} onChange={(event) => update({ description: event.target.value })} /></label>
        </fieldset>
      </section>
      <section role="tabpanel" id="measure-panel-1" aria-labelledby="measure-tab-1" hidden={tab !== "Requirements"} className="panel" tabIndex={0}>
        <div className="workspace-actions measure-heading"><div><h2>{t("measures.associatedRequirements")}</h2>
          <p className="muted">{t("measures.associationNotice")}</p></div>
          {canWrite ? <button type="button" disabled={busy} onClick={() => setPicker(true)}>{t("measures.addRequirements")}</button> : null}
        </div>
        {groups.length ? groups.map(([key, requirements]) => <RequirementGroup key={key} tenantId={tenantId}
          catalogName={catalogs.find((catalog) => catalog.id === requirements[0].catalog_id)?.name}
          requirements={requirements} canWrite={canWrite && !busy}
          onChange={(controlId, description) => update({ requirements: component.requirements.map((item) =>
            item.catalog_id === requirements[0].catalog_id && item.revision_id === requirements[0].revision_id && item.control_id === controlId ? { ...item, description } : item) })}
          onRemove={(controlId) => update({ requirements: component.requirements.filter((item) =>
            item.catalog_id !== requirements[0].catalog_id || item.revision_id !== requirements[0].revision_id || item.control_id !== controlId) })} />)
          : <p className="empty">{t("measures.noAssociatedRequirements")}</p>}
      </section>
      <section role="tabpanel" id="measure-panel-2" aria-labelledby="measure-tab-2" hidden={tab !== "OSCAL Details"} className="panel" tabIndex={0}>
        <h2>{t("measures.oscalDetailsTitle")}</h2>
        <fieldset className="profile-form measure-form" disabled={!canWrite || busy}>
          <label className="field">{t("measures.componentDefinitionTitle")}<input maxLength={255} value={documentTitle} onChange={(event) => setDocumentTitle(event.target.value)} /></label>
        </fieldset>
        <dl className="meta-list">
          <dt>{t("measures.oscalVersion")}</dt><dd>{document.oscal_version}</dd>
          <dt>{t("measures.documentVersion")}</dt><dd>{document.version}</dd>
          <dt>{t("measures.documentLastUpdated")}</dt><dd>{date(document.updated_at)}</dd>
          <dt>{t("measures.documentUuid")}</dt><dd className="mono">{document.oscal_document_uuid}</dd>
          <dt>{t("measures.componentUuid")}</dt><dd className="mono">{savedComponent?.oscal_uuid ?? t("measures.assignedOnSave")}</dd>
          <dt>{t("measures.internalDocumentIdentity")}</dt><dd className="mono">{document.id}</dd>
          <dt>{t("measures.stableComponentIdentity")}</dt><dd className="mono">{component.id ?? t("measures.assignedOnSave")}</dd>
        </dl>
        <p className="muted">{t("measures.componentDefinitionInfo")}</p>
        <label className="field measure-form">{t("measures.componentInDocument")}
          <select value={activeId} disabled={busy} onChange={(event) => {
            const next = components.find((item) => item.clientId === event.target.value);
            setActiveId(event.target.value); setTab("Overview");
            if (next?.id) window.history.replaceState(null, "", `/t/${tenantId}/measures/${document.id}/${next.id}`);
          }}>
            {components.map((item) => <option key={item.clientId} value={item.clientId}>{item.title || t("measures.newComponent")}</option>)}
          </select>
        </label>
        {canWrite ? <div className="workspace-actions">
          <button type="button" className="secondary" disabled={busy} onClick={() => {
            const clientId = crypto.randomUUID();
            setComponents((current) => [...current, { clientId, type: "policy", title: "", description: "", requirements: [] }]);
            setActiveId(clientId); setTab("Overview");
          }}>{t("measures.addComponent")}</button>
          <button type="button" className="danger-action" disabled={busy} onClick={() => void removeComponent()}>{t("measures.deleteComponent")}</button>
          <button type="button" className="danger-action" disabled={busy} onClick={() => void removeDocument()}>{t("measures.deleteDocument")}</button>
        </div> : null}
      </section>
    </>}
  </div>;
}

function RequirementGroup({ tenantId, catalogName, requirements, canWrite, onChange, onRemove }: {
  tenantId: string; catalogName?: string; requirements: ComponentRequirementInput[]; canWrite: boolean;
  onChange: (controlId: string, description: string) => void; onRemove: (controlId: string) => void;
}) {
  const { t, number, errorMessage } = useI18n();
  const { catalog_id: catalogId, revision_id: revisionId } = requirements[0];
  const [data, setData] = useState<{ nodes: ProfileBrowserNode[]; revision: RevisionDetail; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const base = `tenants/${tenantId}/catalogs/${catalogId}/revisions/${revisionId}`;
    Promise.all([
      bffGet<{ nodes: ProfileBrowserNode[] }>(`${base}/profile-browser`, undefined, controller.signal),
      bffGet<RevisionDetail>(base, undefined, controller.signal),
      catalogName ? Promise.resolve(catalogName) :
        bffGet<Catalog>(`tenants/${tenantId}/catalogs/${catalogId}`, undefined, controller.signal).then((catalog) => catalog.name),
    ]).then(([browser, revision, name]) => setData({ nodes: browser.nodes, revision, name }))
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(errorMessage(cause) || t("measures.loadRequirementDetailsError")); });
    return () => controller.abort();
  }, [tenantId, catalogId, revisionId, catalogName, errorMessage, t]);
  return <section className="measure-requirement-group">
    <h3>{data?.name ?? catalogName ?? catalogId} · {data?.revision ? t("measures.requirementGroupRevision", { number: number(data.revision.revision_number) }) : `${t("measures.revision")} ${revisionId}`}</h3>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    {requirements.map((requirement) => <details className="measure-requirement" key={requirement.control_id}>
      <summary><span className="mono">{requirement.control_id}</span> · {data?.nodes.find((node) => node.kind === "control" && node.id === requirement.control_id)?.title ?? t("measures.control")}
        <span className="muted"> · {canWrite ? t("measures.viewEditGuidance") : t("measures.viewGuidance")}</span>
        <span className="measure-guidance-preview">{requirement.description || t("measures.implementationGuidanceRequired")}</span>
      </summary>
      <label className="field measure-form">{t("measures.guidanceFor", { control: requirement.control_id })}
        <textarea required maxLength={50000} rows={4} disabled={!canWrite} value={requirement.description}
          onChange={(event) => onChange(requirement.control_id, event.target.value)} />
      </label>
      {!requirement.description.trim() ? <p className="muted">{t("measures.guidanceRequiredBeforeSave")}</p> : null}
      <MappingControlDetails tenantId={tenantId} catalogId={catalogId} revisionId={revisionId} controlId={requirement.control_id} />
      <RequirementMappingHints tenantId={tenantId} requirement={requirement} />
      {canWrite ? <button type="button" className="secondary" onClick={() => {
        if (window.confirm(t("measures.removeAssociationConfirm", { control: requirement.control_id }))) onRemove(requirement.control_id);
      }}>{t("measures.removeAssociation")}</button> : null}
    </details>)}
  </section>;
}

function RequirementMappingHints({ tenantId, requirement }: { tenantId: string; requirement: ComponentRequirementInput }) {
  const { t, number, enumLabel, errorMessage } = useI18n();
  const [open, setOpen] = useState(false);
  const [mappings, setMappings] = useState<RelatedMapping[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    bffGet<{ items: RelatedMapping[] }>(
      `tenants/${tenantId}/catalogs/${requirement.catalog_id}/revisions/${requirement.revision_id}/controls/${encodeURIComponent(requirement.control_id)}/related-mappings`,
      undefined, controller.signal,
    ).then(({ items }) => setMappings(items)).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(cause) || t("measures.loadRelatedMappingsError"));
    });
    return () => controller.abort();
  }, [open, tenantId, requirement.catalog_id, requirement.revision_id, requirement.control_id, errorMessage, t]);
  return <details onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{t("measures.relatedMappings")}{mappings ? ` (${number(mappings.length)})` : ""}</summary>
    <p className="muted">{t("measures.relatedMappingsNotice")}</p>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    {mappings?.length ? <ul>{mappings.map((mapping) => <li key={`${mapping.collection_id}:${mapping.mapping_uuid}:${mapping.entry_uuid}`}>
      <strong>{mapping.collection_title}</strong> · {enumLabel(mapping.relationship)} ({mapping.relationship}) · {enumLabel(mapping.matching_rationale)} ({mapping.matching_rationale})
      <div>{t("measures.sourceSet")} {mapping.sources.map((control) => `${control.catalog_name} · ${t("measures.revisionNumber", { number: number(control.revision_number) })} · ${control.control_id} ${control.title}`).join("; ")}</div>
      <div>{t("measures.targetSet")} {mapping.targets.map((control) => `${control.catalog_name} · ${t("measures.revisionNumber", { number: number(control.revision_number) })} · ${control.control_id} ${control.title}`).join("; ")}</div>
    </li>)}</ul> : mappings ? <p className="muted">{t("measures.noRelatedMappings")}</p> : !error ? <p role="status">{t("measures.loadingMappings")}</p> : null}
  </details>;
}
