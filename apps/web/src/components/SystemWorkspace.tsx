"use client";

import { useState, type FormEvent } from "react";

import type {
  Catalog,
  ComponentDefinition,
  InformationSystem,
  RevisionSummary,
  SystemComponent,
  SystemSecurityPlan,
} from "@/lib/types";

interface RevisionOption {
  catalog: Catalog;
  revision: RevisionSummary;
}

export function SystemWorkspace({
  tenantId,
  initialSystem,
  initialComponents,
  initialPlans,
  catalogs,
  revisions,
  definitions,
  canWrite,
}: {
  tenantId: string;
  initialSystem: InformationSystem;
  initialComponents: SystemComponent[];
  initialPlans: SystemSecurityPlan[];
  catalogs: Catalog[];
  revisions: RevisionOption[];
  definitions: ComponentDefinition[];
  canWrite: boolean;
}) {
  const [system, setSystem] = useState(initialSystem);
  const [components, setComponents] = useState(initialComponents);
  const [plans, setPlans] = useState(initialPlans);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [componentType, setComponentType] = useState("service");
  const [editingComponent, setEditingComponent] = useState<string | null>(null);
  const [sourceSelection, setSourceSelection] = useState("");
  const [adopting, setAdopting] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [purpose, setPurpose] = useState("");
  const [componentStatus, setComponentStatus] = useState("operational");
  const [componentRemarks, setComponentRemarks] = useState("");
  const [planTitle, setPlanTitle] = useState("");
  const [controlDescription, setControlDescription] = useState("");
  const [baseline, setBaseline] = useState("");
  const [systemIdsText, setSystemIdsText] = useState(
    system.system_ids
      .map((item) => `${item.id}${item["identifier-type"] ? ` | ${item["identifier-type"]}` : ""}`)
      .join("\n"),
  );
  const [informationTypesText, setInformationTypesText] = useState(
    system.information_types.map((item) => `${item.title} | ${item.description}`).join("\n"),
  );

  async function saveSystem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const currentTypes = new Map(system.information_types.map((item) => [item.title, item.uuid]));
      const result = await request<InformationSystem>(
        `/bff/tenants/${tenantId}/systems/${system.id}`,
        "PUT",
        {
          name: system.name,
          description: system.description,
          system_boundary: system.system_boundary,
          system_ids: systemIdsText
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => {
              const [id, identifier_type] = line.split("|").map((part) => part.trim());
              return { id, identifier_type: identifier_type || null };
            }),
          information_types: informationTypesText
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => {
              const [itemTitle, ...rest] = line.split("|").map((part) => part.trim());
              return {
                uuid: currentTypes.get(itemTitle),
                title: itemTitle,
                description: rest.join(" | "),
              };
            }),
          operational_status: system.operational_status,
          status_remarks: system.status_remarks,
          security_sensitivity_level: system.security_sensitivity_level,
        },
      );
      setSystem(result);
      setSystemIdsText(
        result.system_ids
          .map((item) => `${item.id}${item["identifier-type"] ? ` | ${item["identifier-type"]}` : ""}`)
          .join("\n"),
      );
      setInformationTypesText(
        result.information_types.map((item) => `${item.title} | ${item.description}`).join("\n"),
      );
      return "System characteristics saved.";
    });
  }

  async function saveComponent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const body = {
        title,
        description,
        purpose: purpose || null,
        status: componentStatus,
        status_remarks: componentRemarks || null,
      };
      const result = await request<SystemComponent>(
        editingComponent
          ? `/bff/tenants/${tenantId}/systems/${system.id}/components/${editingComponent}`
          : adopting
            ? `/bff/tenants/${tenantId}/systems/${system.id}/components/adopt`
            : `/bff/tenants/${tenantId}/systems/${system.id}/components`,
        editingComponent || adopting ? (editingComponent ? "PUT" : "POST") : "POST",
        editingComponent
          ? body
          : adopting
            ? {
                ...body,
                source_document_id: sourceSelection.split("|")[0],
                source_component_id: sourceSelection.split("|")[1],
              }
            : {
                ...body,
                component_type: componentType,
                is_system_component: componentType === "this-system",
              },
      );
      setComponents((current) =>
        editingComponent
          ? current.map((item) => (item.id === result.id ? result : item))
          : [...current, result],
      );
      resetComponentForm();
      return editingComponent ? "System component updated." : "System component added.";
    });
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const [catalog_id, revision_id] = baseline.split("|");
    if (!catalog_id || !revision_id) return;
    await run(async () => {
      const result = await request<SystemSecurityPlan>(
        `/bff/tenants/${tenantId}/systems/${system.id}/system-security-plans`,
        "POST",
        { catalog_id, revision_id, title: planTitle, control_implementation_description: controlDescription || null },
      );
      setPlans((current) => [...current, result]);
      setPlanTitle("");
      setControlDescription("");
      return "SSP draft created with the selected pinned Catalog revision.";
    });
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setNotice(await action());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The request could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  function chooseReusableComponent(value: string) {
    setSourceSelection(value);
    const [documentId, componentId] = value.split("|");
    const source = definitions
      .find((definition) => definition.id === documentId)
      ?.components.find((item) => item.id === componentId);
    if (source) {
      setTitle(source.title);
      setDescription(source.description);
    }
  }

  function resetComponentForm() {
    setEditingComponent(null);
    setAdopting(false);
    setSourceSelection("");
    setTitle("");
    setDescription("");
    setPurpose("");
    setComponentStatus("operational");
    setComponentRemarks("");
  }

  const selectedSource = sourceSelection.split("|");
  const selectedDefinition = definitions.find((definition) => definition.id === selectedSource[0]);
  const availableRevisions = revisions.filter(
    (item) => item.catalog.latest_revision?.lifecycle_status !== "withdrawn",
  );

  return (
    <div className="workspace">
      <a href={`/t/${tenantId}/systems`}>← Systems</a>
      <h1>{system.name}</h1>
      <p className="muted">
        System facts and components are shared across its SSPs. Each SSP pins one Catalog
        revision and has an independent set of explicit implementation contributions.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}

      <section className="panel">
        <h2>System characteristics</h2>
        <form className="stack" onSubmit={saveSystem}>
          <label className="field">
            System name
            <input
              value={system.name}
              maxLength={255}
              onChange={(event) => setSystem({ ...system, name: event.target.value })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            System description
            <textarea
              value={system.description ?? ""}
              onChange={(event) => setSystem({ ...system, description: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            Authorization boundary description
            <textarea
              value={system.system_boundary ?? ""}
              onChange={(event) => setSystem({ ...system, system_boundary: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            User-provided             User-provided system identifiers (one per line; optional identifier-type URI after “|”)
            <textarea
              value={systemIdsText}
              onChange={(event) => setSystemIdsText(event.target.value)}
              disabled={!canWrite || busy}
              placeholder="Use an identifier and identifier scheme meaningful to your organization."
            />
          </label>
          <label className="field">
            Information types (one per line: title | description)
            <textarea
              value={informationTypesText}
              onChange={(event) => setInformationTypesText(event.target.value)}
              disabled={!canWrite || busy}
              placeholder="Employee identity data | Identity information used by this system."
            />
          </label>
          <label className="field">
            OSCAL System operational status
            <select
              value={system.operational_status ?? ""}
              onChange={(event) => setSystem({ ...system, operational_status: event.target.value || null })}
              disabled={!canWrite || busy}
            >
              <option value="">Not set</option>
              <option value="operational">Operational</option>
              <option value="under-development">Under development</option>
              <option value="under-major-modification">Under major modification</option>
              <option value="disposition">Disposition</option>
              <option value="other">Other</option>
            </select>
          </label>
          {system.operational_status === "other" ? (
            <label className="field">
              Explain the “other” status
              <textarea
                value={system.status_remarks ?? ""}
                onChange={(event) => setSystem({ ...system, status_remarks: event.target.value || null })}
                disabled={!canWrite || busy}
              />
            </label>
          ) : null}
          <label className="field">
            Security sensitivity level (only if explicitly determined)
            <input
              value={system.security_sensitivity_level ?? ""}
              onChange={(event) => setSystem({ ...system, security_sensitivity_level: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          {canWrite ? <button disabled={busy}>Save System characteristics</button> : null}
        </form>
      </section>

      <section className="panel">
        <h2>Concrete System components</h2>
        <p className="muted">
          Components describe actual deployed components. Adopting reusable guidance
          does not assert deployment or control coverage.
        </p>
        {components.length ? (
          <ul className="profile-list">
            {components.map((item) => (
              <li key={item.id}>
                <strong>{item.component.title}</strong>
                {item.is_system_component ? <span> · this-system</span> : null}
                <p>{item.component.description}</p>
                <p className="muted">
                  {item.component.type} · {item.component.status.state}
                  {item.source_snapshot_id ? " · adopted immutable Component Definition snapshot" : ""}
                </p>
                {canWrite ? (
                  <button
                    className="secondary"
                    type="button"
                    onClick={() => {
                      setEditingComponent(item.id);
                      setTitle(item.component.title);
                      setDescription(item.component.description);
                      setPurpose(item.component.purpose ?? "");
                      setComponentStatus(item.component.status.state);
                      setComponentRemarks(item.component.status.remarks ?? "");
                    }}
                  >
                    Edit component
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : <p className="muted">No concrete components have been recorded.</p>}
        {canWrite ? (
          <form className="stack" onSubmit={saveComponent}>
            <h3>{editingComponent ? "Edit component" : adopting ? "Adopt a reusable component" : "Add a concrete component"}</h3>
            {!editingComponent && !adopting ? (
              <label className="field">
                Component type
                <select value={componentType} onChange={(event) => setComponentType(event.target.value)}>
                  <option value="service">Service</option>
                  <option value="software">Software</option>
                  <option value="hardware">Hardware</option>
                  <option value="system">System</option>
                  <option value="interconnection">Interconnection</option>
                  <option value="policy">Policy</option>
                  <option value="physical">Physical</option>
                  <option value="process-procedure">Process / procedure</option>
                  <option value="this-system">This system (system-wide contributions)</option>
                </select>
              </label>
            ) : null}
            {!editingComponent && definitions.length ? (
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setAdopting(!adopting);
                  setEditingComponent(null);
                }}
              >
                {adopting ? "Add a different component" : "Adopt from Our Measures & Controls"}
              </button>
            ) : null}
            {adopting ? (
              <label className="field">
                Reusable Component Definition component
                <select
                  required
                  value={sourceSelection}
                  onChange={(event) => chooseReusableComponent(event.target.value)}
                >
                  <option value="">Select a source component</option>
                  {definitions.flatMap((definition) =>
                    definition.components.map((source) => (
                      <option key={`${definition.id}|${source.id}`} value={`${definition.id}|${source.id}`}>
                        {definition.title} — {source.title}
                      </option>
                    )),
                  )}
                </select>
              </label>
            ) : null}
            {selectedDefinition && adopting ? (
              <p className="muted">
                Source snapshot: {selectedDefinition.title}, component {selectedSource[1]}. The
                full source document is retained immutably.
              </p>
            ) : null}
            <label className="field">
              Component title
              <input required value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label className="field">
              Actual deployment description
              <textarea required value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="field">
              Purpose (optional)
              <input value={purpose} onChange={(event) => setPurpose(event.target.value)} />
            </label>
            <label className="field">
              OSCAL component operational status
              <select value={componentStatus} onChange={(event) => setComponentStatus(event.target.value)}>
                <option value="operational">Operational</option>
                <option value="under-development">Under development</option>
                <option value="disposition">Disposition</option>
                <option value="other">Other</option>
              </select>
            </label>
            {componentStatus === "other" ? (
              <label className="field">
                Explain the “other” status
                <textarea value={componentRemarks} onChange={(event) => setComponentRemarks(event.target.value)} />
              </label>
            ) : null}
            <div className="workspace-actions">
              <button disabled={busy || (adopting && !sourceSelection)}>
                {busy ? "Saving…" : editingComponent ? "Save component" : adopting ? "Adopt component" : "Add component"}
              </button>
              {editingComponent || adopting ? (
                <button className="secondary" type="button" onClick={resetComponentForm}>Cancel</button>
              ) : null}
            </div>
          </form>
        ) : null}
      </section>

      <section className="panel">
        <h2>SSP drafts and pinned baselines</h2>
        <p className="muted">
          A baseline is the complete selected Catalog revision. Documented requirements
          below are a subset, not a reduced baseline or compliance score.
        </p>
        {plans.length ? (
          <ul className="profile-list">
            {plans.map((plan) => (
              <li key={plan.id}>
                <h3>{plan.title}</h3>
                <p>
                  {plan.catalog_name} · pinned revision <span className="mono">{plan.revision_id}</span>
                </p>
                <p className="muted">
                  {plan.documented_control_count} explicitly documented controls of {plan.baseline_control_count} in the baseline
                </p>
                <a className="button" href={`/t/${tenantId}/systems/${system.id}/system-security-plans/${plan.id}`}>
                  Open SSP working state
                </a>
              </li>
            ))}
          </ul>
        ) : <p className="muted">No SSP drafts exist for this System.</p>}
        {canWrite ? (
          <form className="stack" onSubmit={createPlan}>
            <h3>Create SSP draft</h3>
            <label className="field">
              Pinned Catalog revision
              <select required value={baseline} onChange={(event) => setBaseline(event.target.value)}>
                <option value="">Select a Catalog revision</option>
                {availableRevisions.map(({ catalog, revision }) => (
                  <option key={`${catalog.id}|${revision.id}`} value={`${catalog.id}|${revision.id}`}>
                    {catalog.name} · revision {revision.revision_number} · {revision.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              SSP title
              <input required value={planTitle} onChange={(event) => setPlanTitle(event.target.value)} />
            </label>
            <label className="field">
              Control implementation description
              <textarea
                value={controlDescription}
                onChange={(event) => setControlDescription(event.target.value)}
                placeholder="Describe the approach used to document requirement satisfaction."
              />
            </label>
            <button disabled={busy || !baseline}>Create SSP draft</button>
          </form>
        ) : null}
        {catalogs.length === 0 ? <p className="muted">Import a Catalog before creating an SSP.</p> : null}
      </section>
    </div>
  );
}

async function request<T>(
  path: string,
  method: "POST" | "PUT",
  body: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result: unknown = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(readError(result));
  return result as T;
}

function readError(body: unknown): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null && "diagnostics" in detail) {
      const diagnostics = (detail as { diagnostics?: { message?: string }[] }).diagnostics;
      if (diagnostics?.length) return diagnostics.map((item) => item.message).join(" ");
    }
  }
  return "The request could not be completed.";
}
