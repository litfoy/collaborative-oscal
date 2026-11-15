"use client";

import { useMemo, useState, type FormEvent } from "react";

import { ControlBrowser } from "@/components/ControlBrowser";
import type {
  Implementation,
  InformationSystem,
  SystemComponent,
  SystemSecurityPlan,
  SystemSecurityPlanDiagnostic,
  SystemSecurityPlanValidation,
  SystemSecurityPlanVersion,
  RevisionSummary,
  OutlineNode,
  Paged,
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
  revision,
  initialRoot,
  canWrite,
}: {
  tenantId: string;
  system: InformationSystem;
  initialPlan: SystemSecurityPlan;
  components: SystemComponent[];
  initialImplementations: Implementation[];
  initialVersions: SystemSecurityPlanVersion[];
  revision: RevisionSummary;
  initialRoot: Paged<OutlineNode>;
  canWrite: boolean;
}) {
  const [plan, setPlan] = useState(initialPlan);
  const [savedPlan, setSavedPlan] = useState(initialPlan);
  const [tab, setTab] = useState<"baseline" | "implementation" | "validation" | "versions">("baseline");
  const [editingContribution, setEditingContribution] = useState(false);
  const [contributionQuery, setContributionQuery] = useState("");
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
  const dirtyPlan = plan.title !== savedPlan.title || plan.control_implementation_description !== savedPlan.control_implementation_description;
  const pendingContribution = !!selectedId;

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
      setSavedPlan(saved);
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
        try {
          await request(
            `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/implementations/${updated.id}`,
            "POST",
            { system_component_id: componentId },
          );
        } catch (reason) {
          throw new Error(`The Implementation Register record was saved, but could not be included in this SSP: ${reason instanceof Error ? reason.message : "Request failed."}`);
        }
        await refreshPlan();
      }
      setSelectedId("");
      setDescription("");
      setOscalStatus("");
      setStatusExplanation("");
      setEditingContribution(false);
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
      setValidation(null);
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
      return version.created
        ? `Created immutable SSP version ${version.document_version}.`
        : "The working content is unchanged; the existing immutable version was reused.";
    });
  }

  async function refreshPlan() {
    const updated = await getJson<SystemSecurityPlan>(
      `/bff/tenants/${tenantId}/system-security-plans/${plan.id}`,
    );
    setPlan((current) => ({ ...updated, title: current.title, control_implementation_description: current.control_implementation_description }));
    setSavedPlan(updated);
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
    if (selectedId && id !== selectedId && !window.confirm("Discard the current contribution draft?")) return;
    if (id === selectedId) return;
    setSelectedId(id);
    const item = candidates.find((candidate) => candidate.id === id);
    if (!item) return;
    setDescription(item.description);
    setOscalStatus(item.oscal_implementation_status ?? "");
    setStatusExplanation(item.oscal_status_explanation ?? "");
    setComponentId(plan.included_implementations.find((entry) => entry.implementation_id === id)?.system_component_id ?? item.system_component_id ?? "");
  }

  return (
    <div className="workspace system-workspace">
      <a href={`/t/${tenantId}/systems/${system.id}`}>← {system.name}</a>
      <h1>{plan.title}</h1>
      <p className="muted">
        Working state · baseline {plan.catalog_name}, pinned revision {revision.revision_number}
        {revision.source_version ? ` · version ${revision.source_version}` : ""}. The SSP documents actual
        implementations; it does not assert assessment conclusions or compliance.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {dirtyPlan ? <p role="status">Unsaved working state changes. Save before validating or creating a version.</p> : null}
      {pendingContribution ? <p role="status">Save or discard the contribution draft before validating or creating a version. Closing the form preserves the draft.</p> : null}
      <nav className="workspace-tabs" aria-label="SSP sections">
        {([["baseline", "Baseline"], ["implementation", "Control implementation"], ["validation", "Validation"], ["versions", "Versions"]] as const).map(([id, label]) => (
          <button type="button" key={id} aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      <section hidden={tab !== "baseline"}>
        <h2>Baseline</h2>
        <p className="muted">Documentation coverage: {plan.documented_control_count} of {plan.baseline_control_count} controls. This is not a compliance or effectiveness score.</p>
        <ControlBrowser tenantId={tenantId} catalogId={plan.catalog_id} revisionId={plan.revision_id} initialRoot={initialRoot} initialControl={null} documentedControlIds={plan.included_implementations.map((item) => item.oscal_control_id)} />
      </section>
      <section className="panel" hidden={tab !== "implementation"}>
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
        <h2>Requirement-specific contributions</h2>
        <label className="field">Search contributions
          <input type="search" value={contributionQuery} onChange={(event) => setContributionQuery(event.target.value)} />
        </label>
        {plan.included_implementations.length ? (
          <ul className="profile-list">
            {plan.included_implementations.filter((entry) => {
              const implementation = implementations.find((item) => item.id === entry.implementation_id);
              return `${entry.oscal_control_id} ${implementation?.description ?? ""}`.toLowerCase().includes(contributionQuery.toLowerCase());
            }).map((entry) => {
              const implementation = implementations.find((item) => item.id === entry.implementation_id);
              const component = components.find((item) => item.id === entry.system_component_id);
              return (
                <li key={entry.implementation_id}>
                  <strong>{entry.oscal_control_id}</strong>
                  {" · "}
                  Actual component: {component?.component.title ?? "Component unavailable"}
                  <p>Requirement contribution: {implementation?.description || "Implementation description is incomplete."}</p>
                  <p className="muted">
                    Application workflow: {implementation?.status ?? "unknown"} · OSCAL status:{" "}
                    {implementation?.oscal_implementation_status ?? "not selected"}
                  </p>
                  {canWrite ? (
                    <div className="workspace-actions">
                    <button type="button" className="secondary" disabled={busy || !implementation} onClick={() => { chooseImplementation(entry.implementation_id); setEditingContribution(true); }}>Edit contribution</button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => removeImplementation(entry.implementation_id)}
                    >
                      Remove from this SSP
                    </button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : <p className="muted">No Implementation Register records are included yet.</p>}

        {canWrite && !editingContribution ? <button type="button" onClick={() => setEditingContribution(true)}>{selectedId ? "Resume contribution" : "Add contribution"}</button> : null}
        {canWrite && editingContribution ? (
          <form className="stack" onSubmit={includeImplementation}>
            <h3>Explicitly include an existing Implementation Register record</h3>
            <label className="field">
              Requirement contribution from the exact pinned baseline
              <select value={selectedId} onChange={(event) => chooseImplementation(event.target.value)}>
                <option value="">Select a requirement contribution</option>
                {candidates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.oscal_control_id} · {item.description || "No description"}
                    {includedIds.has(item.id) ? " (included)" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Actual system component
              <select value={componentId} disabled={!!selected && includedIds.has(selected.id)} onChange={(event) => setComponentId(event.target.value)}>
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
            <button type="button" className="secondary" onClick={() => setEditingContribution(false)}>Close</button>
            <button type="button" className="secondary" onClick={() => { setSelectedId(""); setComponentId(""); setDescription(""); setOscalStatus(""); setStatusExplanation(""); setEditingContribution(false); }}>Discard draft</button>
          </form>
        ) : null}
        {components.length === 0 ? (
          <p className="muted">Add a concrete System component before including contributions.</p>
        ) : null}
      </section>

      <section className="panel" hidden={tab !== "validation"}>
        <h2>Validation</h2>
        <p>
          OSCAL document validity, baseline references, reported implementation
          statuses, and future assessment conclusions are distinct.
        </p>
        {canWrite ? (
          <div className="workspace-actions">
            <button type="button" className="secondary" onClick={validate} disabled={busy || dirtyPlan || pendingContribution}>
              Validate working state
            </button>
          </div>
        ) : null}
        {validation ? <Diagnostics diagnostics={validation.diagnostics} /> : null}
        <p className="muted">A successful validation does not mean the System is compliant or assessed.</p>
      </section>

      <section className="panel" hidden={tab !== "versions"}>
        <h2>Immutable SSP versions</h2>
        <p className="muted">Versions are stored snapshots of saved working state, not assessments or approvals. Exports use the selected stored snapshot.</p>
        {canWrite ? <button type="button" onClick={createVersion} disabled={busy || dirtyPlan || pendingContribution || (validation !== null && !validation.valid)}>Create immutable SSP version</button> : null}
        {versions.length ? (
          <ul className="profile-list">
            {versions.map((version) => (
              <li key={version.id}>
                <strong>Version {version.document_version}</strong>
                <p className="muted">
                  OSCAL {version.oscal_version} ·{" "}
                  <time dateTime={version.last_modified}>{new Date(version.last_modified).toLocaleString()}</time>
                </p>
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
