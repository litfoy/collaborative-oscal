"use client";

import { useMemo, useState, type FormEvent } from "react";

import { ControlBrowser } from "@/components/ControlBrowser";
import { ApiError } from "@/lib/errors";
import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
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

class PartialAssociationError extends Error {
  constructor(
    message: string,
    readonly staleDetail?: { current_version?: number },
  ) {
    super(message);
    this.name = "PartialAssociationError";
  }
}

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
  const { t, number, date, enumLabel, errorMessage } = useI18n();
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
  const [conflict, setConflict] = useState<{ currentVersion: number } | null>(null);

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
  const validationStale = Boolean(validation && (dirtyPlan || pendingContribution));
  const undocumentedControlCount = Math.max(plan.baseline_control_count - plan.documented_control_count, 0);
  const contributionGroups = useMemo(() => {
    const implementationById = new Map(implementations.map((item) => [item.id, item] as const));
    const componentById = new Map(components.map((item) => [item.id, item] as const));
    const groups = new Map<string, {
      oscalControlId: string;
      entries: Array<{
        implementationId: string;
        implementation: Implementation | undefined;
        component: SystemComponent | undefined;
      }>;
    }>();
    plan.included_implementations.forEach((entry) => {
      const group = groups.get(entry.oscal_control_id) ?? {
        oscalControlId: entry.oscal_control_id,
        entries: [],
      };
      group.entries.push({
        implementationId: entry.implementation_id,
        implementation: implementationById.get(entry.implementation_id),
        component: componentById.get(entry.system_component_id),
      });
      groups.set(entry.oscal_control_id, group);
    });
    return [...groups.values()]
      .map((group) => ({ ...group, entries: group.entries.sort((left, right) => (left.implementation?.description ?? "").localeCompare(right.implementation?.description ?? "")) }))
      .sort((left, right) => left.oscalControlId.localeCompare(right.oscalControlId));
  }, [components, implementations, plan.included_implementations]);
  const filteredGroups = contributionGroups.filter((group) => {
    const haystack = [
      group.oscalControlId,
      ...group.entries.flatMap((entry) => [
        entry.implementation?.description ?? "",
        entry.component?.component.title ?? "",
      ]),
    ].join(" ").toLowerCase();
    return haystack.includes(contributionQuery.toLowerCase());
  });

  async function savePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const saved = await request<SystemSecurityPlan>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}`,
        "PUT",
        {
          expected_version: plan.concurrency_version,
          title: plan.title,
          control_implementation_description: plan.control_implementation_description,
        },
        t,
        errorMessage,
      );
      setPlan(saved);
      setSavedPlan(saved);
      setValidation(null);
      setConflict(null);
      return t("systems.sspWorkingStateSaved");
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
        t,
        errorMessage,
      );
      setImplementations((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setValidation(null);
      const alreadyIncluded = includedIds.has(updated.id);
      if (!alreadyIncluded) {
        try {
          const included = await request<IncludedImplementationResponse>(
            `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/implementations/${updated.id}`,
            "POST",
            {
              expected_version: plan.concurrency_version,
              system_component_id: componentId,
            },
            t,
            errorMessage,
          );
          applyMembershipMutation(
            (current) => [
              ...current,
              {
                implementation_id: included.implementation_id,
                oscal_control_id: included.oscal_control_id,
                system_component_id: included.system_component_id,
              },
            ],
            included.concurrency_version,
          );
        } catch (reason) {
          if (reason instanceof ApiError && reason.kind === "stale_update") {
            throw new PartialAssociationError(
              t("systems.recordSavedButNotIncluded", {
                reason: errorMessage(reason),
              }),
              reason.detail as { current_version?: number } | undefined,
            );
          }
          throw new PartialAssociationError(
            t("systems.recordSavedButNotIncluded", {
              reason:
                reason instanceof Error
                  ? errorMessage(reason)
                  : t("systems.requestFailedSentence"),
            }),
          );
        }
      }
      setSelectedId("");
      setDescription("");
      setOscalStatus("");
      setStatusExplanation("");
      setEditingContribution(false);
      setConflict(null);
      return alreadyIncluded
        ? t("systems.contributionUpdatedNotice")
        : t("systems.contributionAddedNotice");
    });
  }

  async function removeImplementation(implementationId: string) {
    await run(async () => {
      const token = await request<{ concurrency_version: number }>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/implementations/${implementationId}?expected_version=${plan.concurrency_version}`,
        "DELETE",
        undefined,
        t,
        errorMessage,
      );
      applyMembershipMutation(
        (current) => current.filter((item) => item.implementation_id !== implementationId),
        token.concurrency_version,
      );
      setValidation(null);
      setConflict(null);
      return t("systems.contributionRemovedNotice");
    });
  }

  async function validate() {
    await run(async () => {
      const result = await getJson<SystemSecurityPlanValidation>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/validation`,
        t,
        errorMessage,
      );
      setValidation(result);
      return result.valid ? t("systems.validationPassed") : t("systems.validationIssues");
    });
  }

  async function createVersion() {
    await run(async () => {
      const version = await request<SystemSecurityPlanVersion>(
        `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions`,
        "POST",
        { expected_version: plan.concurrency_version },
        t,
        errorMessage,
      );
      if (typeof version.concurrency_version === "number") {
        setPlan((current) => ({ ...current, concurrency_version: version.concurrency_version as number }));
        setSavedPlan((current) => ({ ...current, concurrency_version: version.concurrency_version as number }));
      }
      setVersions((current) => [
        version,
        ...current.filter((item) => item.id !== version.id),
      ]);
      setConflict(null);
      return version.created
        ? t("systems.createdImmutableVersion", { version: version.document_version })
        : t("systems.workingContentUnchanged");
    });
  }

  function applyMembershipMutation(
    mutate: (current: SystemSecurityPlan["included_implementations"]) => SystemSecurityPlan["included_implementations"],
    concurrencyVersion: number,
  ) {
    setPlan((current) => {
      const included = mutate(current.included_implementations);
      return {
        ...current,
        included_implementations: included,
        documented_control_count: new Set(included.map((item) => item.oscal_control_id)).size,
        concurrency_version: concurrencyVersion,
      };
    });
    setSavedPlan((current) => {
      const included = mutate(current.included_implementations);
      return {
        ...current,
        included_implementations: included,
        documented_control_count: new Set(included.map((item) => item.oscal_control_id)).size,
        concurrency_version: concurrencyVersion,
      };
    });
  }

  async function reloadAfterConflict() {
    if (!conflict || busy) return;
    if (!window.confirm(t("assessmentPlans.confirmConflictReload"))) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const [refreshedPlan, refreshedVersions, refreshedValidation] = await Promise.all([
        getJson<SystemSecurityPlan>(
          `/bff/tenants/${tenantId}/system-security-plans/${plan.id}`,
          t,
          errorMessage,
        ),
        getJson<SystemSecurityPlanVersion[]>(
          `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions`,
          t,
          errorMessage,
        ),
        getJson<SystemSecurityPlanValidation>(
          `/bff/tenants/${tenantId}/system-security-plans/${plan.id}/validation`,
          t,
          errorMessage,
        ),
      ]);
      setPlan(refreshedPlan);
      setSavedPlan(refreshedPlan);
      setVersions(refreshedVersions);
      setValidation(refreshedValidation);
      setEditingContribution(false);
      setSelectedId("");
      setComponentId("");
      setDescription("");
      setOscalStatus("");
      setStatusExplanation("");
      setConflict(null);
    } catch (reason) {
      setError(reason instanceof Error ? errorMessage(reason) : t("systems.requestFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setNotice(await action());
    } catch (reason) {
      if (reason instanceof PartialAssociationError) {
        if (reason.staleDetail) {
          setConflict({
            currentVersion: reason.staleDetail.current_version ?? plan.concurrency_version,
          });
        }
        setError(reason.message);
        return;
      }
      if (reason instanceof ApiError && reason.kind === "stale_update") {
        const detail = reason.detail as { current_version?: number } | undefined;
        setConflict({ currentVersion: detail?.current_version ?? plan.concurrency_version });
        setError("");
        return;
      }
      setError(reason instanceof Error ? errorMessage(reason) : t("systems.requestFailed"));
    } finally {
      setBusy(false);
    }
  }

  function chooseImplementation(id: string) {
    if (selectedId && id !== selectedId && !window.confirm(t("systems.discardContributionConfirm"))) return;
    if (id === selectedId) return;
    setSelectedId(id);
    const item = candidates.find((candidate) => candidate.id === id);
    if (!item) return;
    setDescription(item.description);
    setOscalStatus(item.oscal_implementation_status ?? "");
    setStatusExplanation(item.oscal_status_explanation ?? "");
    setComponentId(plan.included_implementations.find((entry) => entry.implementation_id === id)?.system_component_id ?? item.system_component_id ?? "");
  }

  function openRequirement(controlId: string) {
    setContributionQuery(controlId);
    setTab("baseline");
  }

  function openContributions(controlId: string) {
    setContributionQuery(controlId);
    setTab("implementation");
  }

  return (
    <div className="workspace system-workspace">
      <a href={`/t/${tenantId}/systems/${system.id}`}>← {system.name}</a>
      <h1>{plan.title}</h1>
      <p className="muted">
        {t("systems.workingState")} · {t("systems.baseline").toLowerCase()} {plan.catalog_name}, {t("systems.pinnedRevision", { revision: number(revision.revision_number) })}
        {revision.source_version ? ` · ${t("systems.version", { version: revision.source_version })}` : ""}. {t("systems.sspDocumentsActual")}
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {dirtyPlan ? <p role="status">{t("systems.unsavedWorkingChanges")}</p> : null}
      {pendingContribution ? <p role="status">{t("systems.pendingContribution")}</p> : null}
      {conflict ? (
        <div role="alert" className="panel">
          <p>{t("assessmentPlans.conflictDetected", { version: conflict.currentVersion })}</p>
          <p className="muted">{t("assessmentPlans.conflictPreserved")}</p>
          <button type="button" className="danger-action" disabled={busy} onClick={() => void reloadAfterConflict()}>
            {t("assessmentPlans.reloadConfirmedState")}
          </button>
        </div>
      ) : null}
      <nav className="workspace-tabs" aria-label={t("systems.sspSections")}>
        {([["baseline", t("systems.baseline")], ["implementation", t("systems.controlImplementation")], ["validation", t("systems.validation")], ["versions", t("systems.versions")]] as const).map(([id, label]) => (
          <button type="button" key={id} aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      <section hidden={tab !== "baseline"}>
        <h2>{t("systems.baseline")}</h2>
        <p className="muted">{t("systems.documentationCoverage", { documented: number(plan.documented_control_count), baseline: number(plan.baseline_control_count) })}</p>
        <div className="ssp-coverage-cards" role="status">
          <article className="card ssp-coverage-card">
            <h3>{t("systems.baselineControls")}</h3>
            <p className="ssp-coverage-count">{number(plan.baseline_control_count)}</p>
          </article>
          <article className="card ssp-coverage-card">
            <h3>{t("systems.documentedControlsLabel")}</h3>
            <p className="ssp-coverage-count">{number(plan.documented_control_count)}</p>
            <button type="button" className="secondary" onClick={() => openContributions("")}>{t("systems.openContributionsWorkspace")}</button>
          </article>
          <article className="card ssp-coverage-card">
            <h3>{t("systems.undocumentedControlsLabel")}</h3>
            <p className="ssp-coverage-count">{number(undocumentedControlCount)}</p>
          </article>
        </div>
        {contributionGroups.length ? (
          <section className="panel">
            <h3>{t("systems.documentedRequirementDirectory")}</h3>
            <ul className="profile-list">
              {contributionGroups.map((group) => (
                <li key={group.oscalControlId}>
                  <strong>{group.oscalControlId}</strong>
                  <p className="muted">{t("systems.contributionCount", { count: number(group.entries.length) })}</p>
                  <button type="button" className="secondary" onClick={() => openContributions(group.oscalControlId)}>
                    {t("systems.viewImplementationContributions")}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <ControlBrowser tenantId={tenantId} catalogId={plan.catalog_id} revisionId={plan.revision_id} initialRoot={initialRoot} initialControl={null} documentedControlIds={plan.included_implementations.map((item) => item.oscal_control_id)} />
      </section>
      <section className="panel" hidden={tab !== "implementation"}>
        <h2>{t("systems.controlImplementation")}</h2>
        <h3>{t("systems.sspMetadata")}</h3>
        <form className="stack" onSubmit={savePlan}>
          <label className="field">
            {t("systems.sspDocumentTitle")}
            <input
              value={plan.title}
              onChange={(event) => setPlan({ ...plan, title: event.target.value })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            {t("systems.controlImplementationDescription")}
            <textarea
              value={plan.control_implementation_description ?? ""}
              onChange={(event) =>
                setPlan({
                  ...plan,
                  control_implementation_description: event.target.value || null,
                })
              }
              disabled={!canWrite || busy}
              placeholder={t("systems.controlDescriptionPlaceholder")}
            />
          </label>
          {canWrite ? <button disabled={busy}>{t("systems.saveWorkingState")}</button> : null}
        </form>
        <p className="muted">
          {t("systems.explicitlyDocumentedRequirements", { documented: number(plan.documented_control_count), baseline: number(plan.baseline_control_count) })}
        </p>
        <h2>{t("systems.requirementContributions")}</h2>
        <label className="field">{t("systems.searchContributions")}
          <input type="search" value={contributionQuery} onChange={(event) => setContributionQuery(event.target.value)} />
        </label>
        <div className={`system-components-layout${editingContribution && canWrite ? " has-editor" : ""}`}>
          <div>
            {filteredGroups.length ? (
              <ul className="profile-list ssp-contribution-groups">
                {filteredGroups.map((group) => (
                  <li key={group.oscalControlId} className="card ssp-contribution-group">
                    <div className="ssp-contribution-group-heading">
                      <h3>{group.oscalControlId}</h3>
                      <div className="workspace-actions">
                        <span className="muted">{t("systems.contributionCount", { count: number(group.entries.length) })}</span>
                        <button type="button" className="secondary" onClick={() => openRequirement(group.oscalControlId)}>
                          {t("systems.viewRequirement")}
                        </button>
                      </div>
                    </div>
                    <ul className="profile-list">
                      {group.entries.map((entry) => (
                        <li key={entry.implementationId}>
                          <p>{t("systems.requirementContribution")} {entry.implementation?.description || t("systems.implementationDescriptionIncomplete")}</p>
                          <dl className="meta-list">
                            <dt>{t("systems.actualComponent")}</dt>
                            <dd>{entry.component?.component.title ?? t("systems.componentUnavailable")}</dd>
                            <dt>{t("systems.applicationWorkflow")}</dt>
                            <dd>{entry.implementation?.status ? enumLabel(entry.implementation.status) : t("systems.unknown")}</dd>
                            <dt>{t("systems.oscalStatus")}</dt>
                            <dd>{entry.implementation?.oscal_implementation_status ? enumLabel(entry.implementation.oscal_implementation_status) : t("systems.notSelected")}</dd>
                          </dl>
                          {canWrite ? (
                            <div className="workspace-actions">
                              <button type="button" className="secondary" disabled={busy || !entry.implementation} onClick={() => { chooseImplementation(entry.implementationId); setEditingContribution(true); }}>
                                {t("systems.editContribution")}
                              </button>
                              <button type="button" className="secondary" disabled={busy} onClick={() => removeImplementation(entry.implementationId)}>
                                {t("systems.removeFromSsp")}
                              </button>
                            </div>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            ) : plan.included_implementations.length ? (
              <p className="muted">{t("systems.noContributionMatches")}</p>
            ) : (
              <p className="muted">{t("systems.noImplementationRecords")}</p>
            )}
            {canWrite && !editingContribution ? <button type="button" onClick={() => setEditingContribution(true)}>{selectedId ? t("systems.resumeContribution") : t("systems.addContribution")}</button> : null}
          </div>
          {canWrite && editingContribution ? (
            <aside className="panel system-component-editor" aria-live="polite">
          <form className="stack" onSubmit={includeImplementation}>
            <h3>{t("systems.includeExistingRegisterRecord")}</h3>
            <label className="field">
              {t("systems.pinnedBaselineContribution")}
              <select value={selectedId} onChange={(event) => chooseImplementation(event.target.value)}>
                <option value="">{t("systems.selectRequirementContribution")}</option>
                {candidates.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.oscal_control_id} · {item.description || t("systems.noDescription")}
                    {includedIds.has(item.id) ? ` ${t("systems.included")}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("systems.actualSystemComponent")}
              <select value={componentId} disabled={!!selected && includedIds.has(selected.id)} onChange={(event) => setComponentId(event.target.value)}>
                <option value="">{t("systems.selectComponent")}</option>
                {availableComponents.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.component.title}{item.is_system_component ? ` ${t("systems.thisSystemParenthetical")}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("systems.requirementImplementationDescription")}
              <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="field">
              {t("systems.oscalImplementationStatus")}
              <select value={oscalStatus} onChange={(event) => setOscalStatus(event.target.value)}>
                <option value="">{t("systems.selectOscalStatus")}</option>
                {OSCAL_STATUSES.map((status) => <option key={status} value={status}>{enumLabel(status)}</option>)}
              </select>
            </label>
            {["planned", "alternative", "not-applicable"].includes(oscalStatus) ? (
              <label className="field">
                {t("systems.explanationRequired")}
                <textarea value={statusExplanation} onChange={(event) => setStatusExplanation(event.target.value)} />
              </label>
            ) : null}
            <button disabled={busy || !selected || !componentId || !oscalStatus}>
              {selected && includedIds.has(selected.id)
                ? t("systems.saveContributionChanges")
                : t("systems.updateAndInclude")}
            </button>
            <button type="button" className="secondary" onClick={() => setEditingContribution(false)}>{t("systems.close")}</button>
            <button type="button" className="secondary" onClick={() => { setSelectedId(""); setComponentId(""); setDescription(""); setOscalStatus(""); setStatusExplanation(""); setEditingContribution(false); }}>{t("systems.discardDraft")}</button>
          </form>
                {selected ? (
                  <div className="workspace-actions">
                    <button type="button" className="secondary" onClick={() => openRequirement(selected.oscal_control_id)}>
                      {t("systems.viewRequirement")}
                    </button>
                  </div>
                ) : null}
                </aside>
              ) : null}
            </div>
        {components.length === 0 ? (
          <p className="muted">{t("systems.addComponentBeforeContributions")}</p>
        ) : null}
      </section>

      <section className="panel" hidden={tab !== "validation"}>
        <h2>{t("systems.validation")}</h2>
        <p>{t("systems.validationUserSummary")}</p>
        {canWrite ? (
          <div className="workspace-actions">
            <button type="button" className="secondary" onClick={validate} disabled={busy || dirtyPlan || pendingContribution}>
              {t("systems.validateWorkingState")}
            </button>
          </div>
        ) : null}
        {validation ? (
          <section className="panel">
            <h3>{validation.valid ? t("systems.validationResultPass") : t("systems.validationResultNeedsAttention")}</h3>
            <p className="muted">
              {t("systems.validationCoverageChecked", {
                documented: number(validation.documented_control_count),
                baseline: number(validation.baseline_control_count),
              })}
            </p>
            {validationStale ? <p role="status">{t("systems.validationStale")}</p> : null}
            {!validationStale ? <Diagnostics diagnostics={validation.diagnostics} t={t} enumLabel={enumLabel} /> : null}
          </section>
        ) : (
          <p className="muted">{t("systems.validationNotRunYet")}</p>
        )}
        <details className="technical-details">
          <summary>{t("systems.validationTechnicalDetails")}</summary>
          <p className="muted">{t("systems.oscalDistinctions")}</p>
        </details>
        <p className="muted">{t("systems.validationDoesNotAssertCompliance")}</p>
      </section>

      <section className="panel" hidden={tab !== "versions"}>
        <h2>{t("systems.immutableSspVersions")}</h2>
        <p className="muted">{t("systems.versionSnapshotsExplanation")}</p>
        {canWrite ? <button type="button" onClick={createVersion} disabled={busy || dirtyPlan || pendingContribution || (validation !== null && !validation.valid)}>{t("systems.createImmutableSspVersion")}</button> : null}
        {versions.length ? (
          <ul className="profile-list">
            {versions.map((version) => (
              <li key={version.id} className="card">
                <strong>{t("common.version")} {version.document_version}</strong>
                <p className="muted">
                  OSCAL {version.oscal_version} ·{" "}
                  <time dateTime={version.last_modified}>{date(version.last_modified)}</time>
                </p>
                <p className="muted">{t("systems.immutableVersionReference", { reference: version.id })}</p>
                <div className="workspace-actions">
                  <a
                    className="button"
                    href={`/t/${tenantId}/systems/${system.id}/system-security-plans/${plan.id}/versions/${version.id}`}
                  >
                    {t("systems.openHistoricalView")}
                  </a>
                </div>
                <details className="technical-details">
                  <summary>{t("systems.versionTechnicalActions")}</summary>
                  <div className="workspace-actions">
                  <a
                    className="button secondary"
                    href={`/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions/${version.id}/export`}
                  >
                    {t("systems.exportStoredOscalJson")}
                  </a>
                  <a
                    href={`/bff/tenants/${tenantId}/system-security-plans/${plan.id}/versions/${version.id}`}
                    className="muted"
                  >
                    {t("systems.stableSspVersionReference")}
                  </a>
                  </div>
                </details>
                <Diagnostics diagnostics={version.diagnostics} t={t} enumLabel={enumLabel} />
              </li>
            ))}
          </ul>
        ) : <p className="muted">{t("systems.noImmutableVersions")}</p>}
      </section>
    </div>
  );
}

function Diagnostics({ diagnostics, t, enumLabel }: { diagnostics: SystemSecurityPlanDiagnostic[]; t: Translate; enumLabel: (value: string) => string }) {
  if (!diagnostics.length) return <p role="status">{t("systems.noValidationDiagnostics")}</p>;
  return (
    <ul className="diagnostics">
      {diagnostics.map((item, index) => (
        <li key={`${item.code}-${index}`}>
          <strong>{t("systems.statusSeverity", { severity: enumLabel(item.severity), code: item.code })}</strong> — {item.message}
        </li>
      ))}
    </ul>
  );
}

async function request<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body: unknown,
  t: Translate,
  errorMessage: (error: unknown) => string,
): Promise<T> {
  const response = await fetch(path, {
    method,
    ...(body === undefined
      ? {}
      : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  const result: unknown =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (
      response.status === 409 &&
      typeof result === "object" &&
      result !== null &&
      "detail" in result &&
      typeof (result as { detail?: unknown }).detail === "object" &&
      (result as { detail?: { code?: string } }).detail?.code === "stale_update"
    ) {
      throw new ApiError("stale_update", 409, t("errors.stale_update"), (result as { detail: unknown }).detail);
    }
    throw new Error(readError(result, t, errorMessage));
  }
  return result as T;
}

async function getJson<T>(path: string, t: Translate, errorMessage: (error: unknown) => string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  const result: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (
      response.status === 409 &&
      typeof result === "object" &&
      result !== null &&
      "detail" in result &&
      typeof (result as { detail?: unknown }).detail === "object" &&
      (result as { detail?: { code?: string } }).detail?.code === "stale_update"
    ) {
      throw new ApiError("stale_update", 409, t("errors.stale_update"), (result as { detail: unknown }).detail);
    }
    throw new Error(readError(result, t, errorMessage));
  }
  return result as T;
}

function readError(body: unknown, t: Translate, errorMessage: (error: unknown) => string): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null && "diagnostics" in detail) {
      const diagnostics = (detail as { diagnostics?: { message?: string }[] }).diagnostics;
      if (diagnostics?.length) return diagnostics.map((item) => item.message).join(" ");
    }
  }
  return errorMessage(body) || t("systems.requestFailed");
}

type IncludedImplementationResponse = {
  implementation_id: string;
  system_component_id: string;
  oscal_control_id: string;
  concurrency_version: number;
};
