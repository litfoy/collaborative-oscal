"use client";

import { useEffect, useState } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import { MappingControlPicker } from "@/components/MappingControlPicker";
import type {
  Catalog,
  ComponentDefinition,
  ComponentDefinitionInput,
  ComponentRequirement,
  Paged,
  RelatedMapping,
  ReusableComponent,
  ReusableComponentInput,
  RevisionSummary,
} from "@/lib/types";

const COMPONENT_TYPES = [
  ["policy", "Policy"],
  ["process-procedure", "Process or procedure"],
  ["service", "Service"],
  ["software", "Software"],
  ["hardware", "Hardware"],
  ["physical", "Physical"],
  ["plan", "Plan"],
  ["guidance", "Guidance"],
  ["standard", "Standard"],
] as const;

type DraftComponent = ReusableComponentInput & { clientId: string };
const emptyComponent = (): DraftComponent => ({
  clientId: crypto.randomUUID(),
  type: "policy",
  title: "",
  description: "",
  requirements: [],
});

export function ComponentDefinitionWorkspace({
  tenantId,
  initialDefinitions,
  catalogs: initialCatalogs,
  catalogTotal,
  canWrite,
}: {
  tenantId: string;
  initialDefinitions: ComponentDefinition[];
  catalogs: Catalog[];
  catalogTotal: number;
  canWrite: boolean;
}) {
  const [definitions, setDefinitions] = useState(initialDefinitions);
  const [catalogs, setCatalogs] = useState(initialCatalogs);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = definitions.find((item) => item.id === selectedId) ?? null;
  const [title, setTitle] = useState("");
  const [components, setComponents] = useState<DraftComponent[]>([]);
  const [baseline, setBaseline] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newType, setNewType] = useState<string>("policy");
  const [newDescription, setNewDescription] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const snapshot = JSON.stringify({ title: title.trim(), components });
  const dirty = Boolean(selected && snapshot !== baseline);
  const valid = title.trim().length > 0 && components.length > 0 && components.every((component) =>
    component.title.trim().length > 0 && component.type.trim().length > 0 &&
    component.requirements.every((item) => item.description.trim().length > 0),
  );

  function open(definition: ComponentDefinition) {
    setSelectedId(definition.id);
    setTitle(definition.title);
    const draft = definition.components.map((component) => ({
      ...component,
      clientId: component.id,
      requirements: component.requirements.map((requirement) => ({ ...requirement })),
    }));
    setComponents(draft);
    setBaseline(JSON.stringify({ title: definition.title, components: draft }));
    setError(null);
    setStatus(null);
  }

  function updateComponent(clientId: string, patch: Partial<DraftComponent>) {
    setComponents((current) =>
      current.map((component) =>
        component.clientId === clientId ? { ...component, ...patch } : component,
      ),
    );
  }

  async function create() {
    if (!canWrite || !newTitle.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await bffWrite<ComponentDefinition>(
        "POST",
        `tenants/${tenantId}/component-definitions`,
        {
          title: newTitle.trim(),
          type: newType,
          description: newDescription,
          requirements: [],
        },
      );
      setDefinitions((current) => [created, ...current]);
      setNewTitle("");
      setNewDescription("");
      open(created);
      setStatus("Measure created.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to create the measure.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!selected || !canWrite || !dirty || !valid || busy) return;
    setBusy(true);
    setError(null);
    setStatus(null);
    const body: ComponentDefinitionInput = {
      title: title.trim(),
      components: components.map(({ clientId: _clientId, ...component }) => component),
    };
    try {
      const saved = await bffWrite<ComponentDefinition>(
        "PUT",
        `tenants/${tenantId}/component-definitions/${selected.id}`,
        body,
      );
      setDefinitions((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      open(saved);
      setStatus("Measure saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to save the measure.");
    } finally {
      setBusy(false);
    }
  }

  async function removeDocument() {
    if (!selected || busy || !window.confirm(`Permanently delete “${selected.title}”?`)) return;
    setBusy(true);
    setError(null);
    try {
      await bffWrite(
        "DELETE",
        `tenants/${tenantId}/component-definitions/${selected.id}`,
        {},
      );
      setDefinitions((current) => current.filter((item) => item.id !== selected.id));
      setSelectedId(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete the document.");
    } finally {
      setBusy(false);
    }
  }

  async function removeComponent(component: DraftComponent) {
    if (!selected || busy) return;
    if (!component.id) {
      if (!window.confirm(`Remove “${component.title || "this component"}” from the unsaved document?`)) {
        return;
      }
      setComponents((current) => current.filter((item) => item.clientId !== component.clientId));
      return;
    }
    if (!window.confirm(`Permanently delete “${component.title}”?`)) return;
    setBusy(true);
    setError(null);
    try {
      await bffWrite(
        "DELETE",
        `tenants/${tenantId}/component-definitions/${selected.id}/components/${component.id}`,
        {},
      );
      if (selected.components.length === 1) {
        setDefinitions((current) => current.filter((item) => item.id !== selected.id));
        setSelectedId(null);
      } else {
        const refreshed = await bffGet<ComponentDefinition>(
          `tenants/${tenantId}/component-definitions/${selected.id}`,
        );
        setDefinitions((current) => [
          refreshed,
          ...current.filter((item) => item.id !== refreshed.id),
        ]);
        open(refreshed);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to delete the component.");
    } finally {
      setBusy(false);
    }
  }

  async function loadMoreCatalogs() {
    setCatalogLoading(true);
    try {
      const page = await bffGet<Paged<Catalog>>(`tenants/${tenantId}/catalogs`, {
        limit: 200,
        offset: catalogs.length,
      });
      setCatalogs((current) => [...current, ...page.items]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load additional catalogs.");
    } finally {
      setCatalogLoading(false);
    }
  }

  return (
    <div className="profile-workspace">
      {canWrite ? (
        <section className="panel">
          <h2>Create a reusable measure</h2>
          <label className="field">
            Measure title
            <input maxLength={255} value={newTitle} onChange={(event) => setNewTitle(event.target.value)} />
          </label>
          <label className="field">
            Component type
            <select value={newType} onChange={(event) => setNewType(event.target.value)}>
              {COMPONENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="field">
            Reusable description
            <textarea maxLength={50000} rows={3} value={newDescription}
              onChange={(event) => setNewDescription(event.target.value)} />
          </label>
          <button type="button" disabled={!newTitle.trim() || busy} onClick={() => void create()}>
            {busy ? "Creating…" : "Create measure"}
          </button>
        </section>
      ) : <p className="muted">You need catalog:write permission to create or edit measures.</p>}

      <section className="panel">
        <h2>Existing measures</h2>
        {definitions.length === 0 ? <p className="muted">No reusable measures yet.</p> : (
          <ul className="profile-list">
            {definitions.flatMap((definition) => definition.components.map((component) => (
              <li className="panel" key={component.id}>
                <h3>{component.title}</h3>
                <p>{component.type} · {component.requirements.length} associated requirements</p>
                <button type="button" onClick={() => open(definition)}>
                  {canWrite ? "Edit measure" : "View measure"}
                </button>
              </li>
            )))}
          </ul>
        )}
        {catalogs.length < catalogTotal ? (
          <button type="button" className="secondary" disabled={catalogLoading}
            onClick={() => void loadMoreCatalogs()}>
            {catalogLoading ? "Loading…" : `Load more catalogs (${catalogTotal - catalogs.length} remaining)`}
          </button>
        ) : null}
      </section>

      {selected ? (
        <section className="panel">
          <nav className="breadcrumbs" aria-label="Breadcrumb">
            <span>Our Measures &amp; Controls</span> › <span aria-current="page">{selected.title}</span>
          </nav>
          <div className="workspace-actions">
            <h2>{canWrite ? "Edit measure" : "Measure details"}</h2>
            <span role="status">{busy ? "Saving…" : dirty ? "Unsaved changes" : status ?? "Saved"}</span>
          </div>
          {error ? <p role="alert" className="alert">{error}</p> : null}
          <fieldset className="profile-form" disabled={!canWrite || busy}>
            <label className="field">
              Component Definition title
              <input maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            {components.map((component) => (
              <MeasureEditor
                key={component.clientId}
                tenantId={tenantId}
                catalogs={catalogs}
                component={component}
                canWrite={canWrite && !busy}
                onChange={(patch) => updateComponent(component.clientId, patch)}
                onDelete={() => void removeComponent(component)}
              />
            ))}
            {canWrite ? (
              <button type="button" className="secondary" disabled={busy}
                onClick={() => setComponents((current) => [...current, emptyComponent()])}>
                Add component to this document
              </button>
            ) : null}
          </fieldset>
          <div className="workspace-actions">
            {canWrite ? <button type="button" disabled={!dirty || !valid || busy} onClick={() => void save()}>
              {busy ? "Saving…" : "Save changes"}
            </button> : null}
            {!dirty ? <a className="button secondary"
              href={`/bff/tenants/${tenantId}/component-definitions/${selected.id}/export`}>
              Export OSCAL Component Definition
            </a> : <span className="muted">Save before exporting.</span>}
          </div>
          <details className="mapping-danger-zone">
            <summary>Technical identity and document lifecycle</summary>
            <dl className="meta-list">
              <dt>Internal document identity</dt><dd className="mono">{selected.id}</dd>
              <dt>OSCAL document UUID</dt><dd className="mono">{selected.oscal_document_uuid}</dd>
              <dt>OSCAL version</dt><dd>{selected.oscal_version}</dd>
              <dt>Document version</dt><dd>{selected.version}</dd>
            </dl>
            {canWrite ? <button type="button" className="danger-action" disabled={busy}
              onClick={() => void removeDocument()}>Delete this document</button> : null}
            <p className="muted">
              This POC stores only the current document. Edits replace its OSCAL document UUID;
              internal component identities and unchanged component UUIDs remain stable.
            </p>
          </details>
        </section>
      ) : null}
    </div>
  );
}

function MeasureEditor({
  tenantId,
  catalogs,
  component,
  canWrite,
  onChange,
  onDelete,
}: {
  tenantId: string;
  catalogs: Catalog[];
  component: DraftComponent;
  canWrite: boolean;
  onChange: (patch: Partial<DraftComponent>) => void;
  onDelete: () => void;
}) {
  const initialRequirement = component.requirements[0];
  const [catalogId, setCatalogId] = useState(
    initialRequirement?.catalog_id ?? catalogs.find((catalog) => catalog.latest_revision)?.id ?? "",
  );
  const catalog = catalogs.find((item) => item.id === catalogId);
  const [revisionId, setRevisionId] = useState(initialRequirement?.revision_id ?? catalog?.latest_revision?.id ?? "");
  const [revisionState, setRevisionState] = useState<{ catalogId: string; items: RevisionSummary[] } | null>(null);
  const [revisionError, setRevisionError] = useState<string | null>(null);
  const revisions = revisionState?.catalogId === catalogId ? revisionState.items : [];
  const selectedRequirements = component.requirements.filter(
    (item) => item.catalog_id === catalogId && item.revision_id === revisionId,
  );
  const selectedIds = selectedRequirements.map((item) => item.control_id);

  useEffect(() => {
    if (!catalogId) return;
    const controller = new AbortController();
    bffGet<Paged<RevisionSummary>>(
      `tenants/${tenantId}/catalogs/${catalogId}/revisions`,
      { limit: 200, offset: 0 },
      controller.signal,
    ).then((result) => {
      setRevisionState({ catalogId, items: result.items });
      setRevisionError(null);
      setRevisionId((current) =>
        result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? "",
      );
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setRevisionError(cause instanceof Error ? cause.message : "Unable to load catalog revisions.");
      }
    });
    return () => controller.abort();
  }, [tenantId, catalogId]);

  function selectControls(ids: string[]) {
    const existing = new Map(selectedRequirements.map((item) => [item.control_id, item]));
    const next = ids.map((control_id) => existing.get(control_id) ?? {
      catalog_id: catalogId,
      revision_id: revisionId,
      control_id,
      description: "",
    });
    onChange({
      requirements: [
        ...component.requirements.filter(
          (item) => item.catalog_id !== catalogId || item.revision_id !== revisionId,
        ),
        ...next,
      ],
    });
  }

  return (
    <section className="panel">
      <h3>{component.title || "New component"}</h3>
      <label className="field">Measure title
        <input maxLength={255} value={component.title}
          onChange={(event) => onChange({ title: event.target.value })} />
      </label>
      <label className="field">Component type
        <select value={component.type} onChange={(event) => onChange({ type: event.target.value })}>
          {COMPONENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label className="field">Reusable description
        <textarea maxLength={50000} rows={3} value={component.description}
          onChange={(event) => onChange({ description: event.target.value })} />
      </label>
      <h4>Normative requirements</h4>
      <p className="muted">Each selected control is explicitly associated. Related mappings are advisory only.</p>
      <div className="mapping-control-filters">
        <label className="field">Catalog
          <select value={catalogId} onChange={(event) => {
            const nextCatalogId = event.target.value;
            setCatalogId(nextCatalogId);
            setRevisionId(catalogs.find((item) => item.id === nextCatalogId)?.latest_revision?.id ?? "");
          }}>
            {catalogs.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="field">Catalog revision
          <select value={revisionId} onChange={(event) => setRevisionId(event.target.value)}>
            {revisions.map((revision) => <option key={revision.id} value={revision.id}>
              Revision {revision.revision_number} · {revision.lifecycle_status}
            </option>)}
          </select>
        </label>
      </div>
      {revisionError ? <p role="alert" className="alert">{revisionError}</p> : null}
      {catalogId && revisionId ? <MappingControlPicker
        key={`${catalogId}:${revisionId}`}
        tenantId={tenantId}
        catalogId={catalogId}
        revisionId={revisionId}
        label={catalog?.name ?? "Catalog"}
        selected={selectedIds}
        disabled={!canWrite}
        onChange={selectControls}
        onControlTitles={() => undefined}
      /> : <p className="muted">Import a catalog revision before associating requirements.</p>}
      {selectedRequirements.map((requirement) => (
        <div className="panel" key={`${requirement.catalog_id}:${requirement.revision_id}:${requirement.control_id}`}>
          <p>
            <a href={`/t/${tenantId}/catalogs/${requirement.catalog_id}?revision=${requirement.revision_id}`}>
              {catalog?.name ?? "Catalog"} · <span className="mono">{requirement.control_id}</span>
            </a>
          </p>
          <label className="field">
            How this measure addresses {requirement.control_id}
            <textarea maxLength={50000} rows={3} required value={requirement.description}
              onChange={(event) => onChange({
                requirements: component.requirements.map((item) =>
                  item.catalog_id === requirement.catalog_id &&
                  item.revision_id === requirement.revision_id &&
                  item.control_id === requirement.control_id
                    ? { ...item, description: event.target.value } : item,
                ),
              })} />
          </label>
          <RequirementMappingHints
            tenantId={tenantId}
            requirement={requirement}
          />
        </div>
      ))}
      {canWrite ? <button type="button" className="secondary"
        onClick={onDelete}>Delete component</button> : null}
      {component.id ? <p className="muted">Stable component identity: <span className="mono">{component.id}</span></p> : null}
    </section>
  );
}

function RequirementMappingHints({
  tenantId,
  requirement,
}: {
  tenantId: string;
  requirement: ComponentRequirement;
}) {
  const [mappings, setMappings] = useState<RelatedMapping[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    bffGet<{ items: RelatedMapping[] }>(
      `tenants/${tenantId}/catalogs/${requirement.catalog_id}/revisions/${requirement.revision_id}/controls/${encodeURIComponent(requirement.control_id)}/related-mappings`,
      undefined,
      controller.signal,
    ).then(({ items }) => {
      setMappings(items);
      setError(null);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Unable to load related mappings.");
      }
    });
    return () => controller.abort();
  }, [tenantId, requirement.catalog_id, requirement.revision_id, requirement.control_id]);
  return (
    <details>
      <summary>Related controls in existing mappings ({mappings.length})</summary>
      {error ? <p role="alert" className="alert">{error}</p> : null}
      {mappings.length ? <ul>{mappings.map((mapping) => (
        <li key={`${mapping.collection_id}:${mapping.mapping_uuid}:${mapping.entry_uuid}`}>
          <strong>{mapping.collection_title}</strong> · {mapping.relationship} · {mapping.matching_rationale}
          <p>Related controls: {[...mapping.sources, ...mapping.targets]
            .map((control) => `${control.catalog_name} ${control.control_id}`).join("; ")}</p>
        </li>
      ))}</ul>
        : <p className="muted">No related mappings. Mappings never add requirements automatically.</p>}
    </details>
  );
}
