"use client";

import { useMemo, useState, type FormEvent } from "react";

import type {
  Implementation,
  InformationSystem,
  SystemComponent,
  SystemSecurityPlan,
  SystemSecurityPlanDiagnostic,
  SystemSecurityPlanValidation,
  SystemSecurityPlanVersion,
} from "@/lib/types";

const OSCAL_STATUSES = [
  "implemented",
  "partial",
  "planned",
  "alternative",
  "not-applicable",
] as const;

export function SystemSecurityPlanWorkspace({
  tenantId,
  system,
  initialPlan,
  components,
  initialImplementations,
  initialVersions,
  canWrite,
}: {
  tenantId: string;
  system: InformationSystem;
  initialPlan: SystemSecurityPlan;
  components: SystemComponent[];
  initialImplementations: Implementation[];
  initialVersions: SystemSecurityPlanVersion[];
  canWrite: boolean;
}) {
  const [plan, setPlan] = useState(initialPlan);
  const [implementations, setImplementations] = useState(initialImplementations);
  const [versions, setVersions] = useState(initialVersions);
  const [validation, setValidation] = useState<SystemSecurityPlanValidation | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [componentId, setComponentId] = useState("");
  const [description, setDescription] = useState("");
  const [oscalStatus, setOscalStatus] = useState("");
  const [statusExplanation, setStatusExplanation] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const candidates = useMemo(
    () =>
      implementations.filter(
        (item) =>
          item.catalog_id === plan.catalog_id &&
          item.revision_id === plan.revision_id &&
          (!item.system_id || item.system_id === system.id),
      ),
    [implementations, plan.catalog_id, plan.revision_id, system.id],
  );
  const selected = candidates.find((item) => item.id === selectedId);
  const includedIds = new Set(plan.included_implementations.map((item) => item.implementation_id));
  const availableComponents = components;

  async function savePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const saved = await request<SystemSecurityPlan>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}`,
        "PUT",
        {
          title: plan.title,
          control_implementation_description: plan.control_implementation_description,
        },
      );
      setPlan(saved);
      setValidation(null);
      return "SSP working state saved.";
    });
  }

  async function includeImplementation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !componentId || !oscalStatus) return;
    await run(async () => {
      const updated = await request<Implementation>(
        `/bff/tenants/${tenantId}/implementations/${selected.id}`,
        "PUT",
        {
          description,
          status: selected.status,
          evidence_references: selected.evidence_references,
          responsibilities: selected.responsibilities,
          oscal_implementation_status: oscalStatus,
          oscal_status_explanation: statusExplanation || null,
        },
      );
      setImplementations((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setValidation(null);
      const alreadyIncluded = includedIds.has(updated.id);
      if (!alreadyIncluded) {
        await request(
          `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/implementations/${updated.id}`,
          "POST",
          { system_component_id: componentId },
        );
        await refreshPlan();
      }
      setSelectedId("");
      setDescription("");
      setOscalStatus("");
      setStatusExplanation("");
      return alreadyIncluded
        ? "Requirement contribution updated in the Implementation Register."
        : "The requirement contribution was explicitly added to this SSP.";
    });
  }

  async function removeImplementation(implementationId: string) {
    await run(async () => {
      await request(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/implementations/${implementationId}`,
        "DELETE",
      );
      await refreshPlan();
      return "Contribution removed from this SSP. The Implementation Register record remains.";
    });
  }

  async function validate() {
    await run(async () => {
      const result = await getJson<SystemSecurityPlanValidation>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/validation`,
      );
      setValidation(result);
      return result.valid ? "The current draft passes configured validation." : "Validation found issues to address.";
    });
  }

  async function createVersion() {
    await run(async () => {
      const version = await request<SystemSecurityPlanVersion>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions`,
        "POST",
        {},
      );
      setVersions((current) => [
        version,
        ...current.filter((item) => item.id !== version.id),
      ]);
      setValidation(await getJson<SystemSecurityPlanValidation>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/validation`,
      ));
      return version.created
        ? `Created immutable SSP version ${version.document_version}.`
        : "The working content is unchanged; the existing immutable version was reused.";
    });
  }

  async function refreshPlan() {
    const updated = await getJson<SystemSecurityPlan>(
      `/bff/tenants/${tenantId}/system-security-plans/${plan.id}`,
    );
    setPlan(updated);
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

  function chooseImplementation(id: string) {
    setSelectedId(id);
    const item = candidates.find((candidate) => candidate.id === id);
    if (!item) return;
    setDescription(item.description);
    setOscalStatus(item.oscal_implementation_status ?? "");
    setStatusExplanation(item.oscal_status_explanation ?? "");
    setComponentId(item.system_component_id ?? "");
  }

  return (
    <div className="workspace">
      <a href={`/t/${tenantId}/systems/${system.id}`}>← {system.name}</a>
      <h1>{plan.title}</h1>
      <p className="muted">
        Working state · baseline {plan.catalog_name}, pinned revision{" "}
        <span className="mono">{plan.revision_id}</span>. The SSP documents actual
        implementations; it does not assert assessment conclusions or compliance.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}

      <section className="panel">
        <h2>Working state</h2>
        <form className="stack" onSubmit={savePlan}>
          <label className="field">
            SSP document title
            <input
              value={plan.title}
              onChange={(event) => setPlan({ ...plan, title: event.target.value })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            Control implementation description
            <textarea
              value={plan.control_implementation_description ?? ""}
              onChange={(event) =>
                setPlan({
                  ...plan,
                  control_implementation_description: event.target.value || null,
                })
              }
              disabled={!canWrite || busy}
              placeholder="Describe the approach used to document requirement satisfaction."
            />
          </label>
          {canWrite ? <button disabled={busy}>Save working state</button> : null}
        </form>
        <p className="muted">
          Explicitly documented requirements: {plan.documented_control_count} of{" "}
          {plan.baseline_control_count} baseline controls. This is documentation
          coverage, not a compliance score.
        </p>
      </section>

      <section className="panel">
        <h2>Requirement-specific contributions</h2>
        {plan.included_implementations.length ? (
          <ul className="profile-list">
            {plan.included_implementations.map((entry) => {
              const implementation = implementations.find((item) => item.id === entry.implementation_id);
              const component = components.find((item) => item.id === entry.system_component_id);
              return (
                <li key={entry.implementation_id}>
                  <strong>{entry.oscal_control_id}</strong>
                  {" · "}
                  {component?.component.title ?? "Component"}
                  <p>{implementation?.description || "Implementation description is incomplete."}</p>
                  <p className="muted">
                    Application workflow: {implementation?.status ?? "unknown"} · OSCAL status:{" "}
                    {implementation?.oscal_implementation_status ?? "not selected"}
                  </p>
                  {canWrite ? (
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => removeImplementation(entry.implementation_id)}
                    >
                      Remove from this SSP
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : <p className="muted">No Implementation Register records are included yet.</p>}

        {canWrite ? (
          <form className="stack" onSubmit={includeImplementation}>
            <h3>Explicitly include an existing Implementation Register record</h3>
            <label className="field">
              Requirement contribution from the exact pinned baseline
              <select value={selectedId} onChange={(event) => chooseImplementation(event.target.value)}>
                <option value="">Select a requirement contribution</option>
                {candidates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.oscal_control_id} · {item.description || "No description"}
                    {includedIds.has(item.id) ? " (included; selecting updates it)" : ""} · {item.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Concrete system component (select explicitly)
              <select value={componentId} onChange={(event) => setComponentId(event.target.value)}>
                <option value="">Select a component</option>
                {availableComponents.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.component.title}{item.is_system_component ? " (this-system)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Requirement-specific implementation description
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="field">
              OSCAL implementation status (separate from application workflow status)
              <select value={oscalStatus} onChange={(event) => setOscalStatus(event.target.value)}>
                <option value="">Select an OSCAL status</option>
                {OSCAL_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
              </select>
            </label>
            {["planned", "alternative", "not-applicable"].includes(oscalStatus) ? (
              <label className="field">
                Explanation required for this state
                <textarea value={statusExplanation} onChange={(event) => setStatusExplanation(event.target.value)} />
              </label>
            ) : null}
            <button disabled={busy || !selected || !componentId || !oscalStatus}>
              {selected && includedIds.has(selected.id)
                ? "Save requirement contribution changes"
                : "Update record and include in SSP"}
            </button>
          </form>
        ) : null}
        {components.length === 0 ? (
          <p className="muted">Add a concrete System component before including contributions.</p>
        ) : null}
      </section>

      <section className="panel">
        <h2>Validation and version creation</h2>
        <p>
          OSCAL document validity, baseline references, reported implementation
          statuses, and future assessment conclusions are distinct.
        </p>
        {canWrite ? (
          <div className="workspace-actions">
            <button type="button" className="secondary" onClick={validate} disabled={busy}>
              Validate working state
            </button>
            <button
              type="button"
              onClick={createVersion}
              disabled={busy || (validation !== null && !validation.valid)}
            >
              Create immutable SSP version
            </button>
          </div>
        ) : null}
        {validation ? <Diagnostics diagnostics={validation.diagnostics} /> : null}
        <p className="muted">A successful validation does not mean the System is compliant or assessed.</p>
      </section>

      <section className="panel">
        <h2>Immutable SSP versions</h2>
        {versions.length ? (
          <ul className="profile-list">
            {versions.map((version) => (
              <li key={version.id}>
                <strong>Version {version.document_version}</strong>
                <p className="muted">
                  OSCAL {version.oscal_version} · {version.oscal_document_uuid} ·{" "}
                  <time dateTime={version.last_modified}>{new Date(version.last_modified).toLocaleString()}</time>
                </p>
                <p className="mono">SHA-256 {version.content_sha256}</p>
                <div className="workspace-actions">
                  <a
                    className="button secondary"
                    href={`/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions/${version.id}/export`}
                  >
                    Export stored OSCAL JSON
                  </a>
                  <a
                    href={`/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions/${version.id}`}
                    className="muted"
                  >
                    Stable SSP version reference
                  </a>
                </div>
                <Diagnostics diagnostics={version.diagnostics} />
              </li>
            ))}
          </ul>
        ) : <p className="muted">No immutable versions exist. The working state can still be incomplete.</p>}
      </section>
    </div>
  );
}

function Diagnostics({ diagnostics }: { diagnostics: SystemSecurityPlanDiagnostic[] }) {
  if (!diagnostics.length) return <p role="status">No validation diagnostics.</p>;
  return (
    <ul className="diagnostics">
      {diagnostics.map((item, index) => (
        <li key={`${item.code}-${index}`}>
          <strong>{item.severity}: {item.code}</strong> — {item.message}
        </li>
      ))}
    </ul>
  );
}

async function request<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    ...(body === undefined
      ? {}
      : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  const result: unknown =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(readError(result));
  return result as T;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  const result: unknown = await response.json().catch(() => null);
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
