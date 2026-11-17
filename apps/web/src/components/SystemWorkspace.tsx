"use client";

import { useState, type FormEvent } from "react";

import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
import type {
  AssessmentResult,
  AssessmentPlan,
  Catalog,
  ComponentDefinition,
  InformationSystem,
  RevisionSummary,
  SystemComponent,
  SystemSecurityPlan,
  SystemSecurityPlanVersion,
} from "@/lib/types";

interface RevisionOption {
  catalog: Catalog;
  revision: RevisionSummary;
}

const EMPTY_COMPONENT_DRAFT = JSON.stringify({
  componentType: "service",
  editingComponent: null,
  sourceSelection: "",
  adopting: false,
  title: "",
  description: "",
  purpose: "",
  componentStatus: "",
  componentRemarks: "",
});

export function SystemWorkspace({
  tenantId,
  initialSystem,
  initialComponents,
  initialPlans,
  initialAssessmentPlans,
  initialAssessmentResults,
  initialVersions,
  planRevisions,
  catalogs,
  revisions,
  definitions,
  canWrite,
}: {
  tenantId: string;
  initialSystem: InformationSystem;
  initialComponents: SystemComponent[];
  initialPlans: SystemSecurityPlan[];
  initialAssessmentPlans: AssessmentPlan[];
  initialAssessmentResults: AssessmentResult[];
  initialVersions: Record<string, SystemSecurityPlanVersion[]>;
  planRevisions: Record<string, RevisionSummary>;
  catalogs: Catalog[];
  revisions: RevisionOption[];
  definitions: ComponentDefinition[];
  canWrite: boolean;
}) {
  const { t, number, enumLabel, errorMessage } = useI18n();
  const [system, setSystem] = useState(initialSystem);
  const [components, setComponents] = useState(initialComponents);
  const [plans, setPlans] = useState(initialPlans);
  const [assessmentPlans, setAssessmentPlans] = useState(initialAssessmentPlans);
  const [assessmentResults, setAssessmentResults] = useState(initialAssessmentResults);
  const [tab, setTab] = useState<"overview" | "components" | "plans">("overview");
  const [componentForm, setComponentForm] = useState(false);
  const [planForm, setPlanForm] = useState(false);
  const [assessmentPlanForm, setAssessmentPlanForm] = useState(false);
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
  const [componentStatus, setComponentStatus] = useState("");
  const [componentRemarks, setComponentRemarks] = useState("");
  const [componentDraftBaseline, setComponentDraftBaseline] = useState(EMPTY_COMPONENT_DRAFT);
  const [planTitle, setPlanTitle] = useState("");
  const [controlDescription, setControlDescription] = useState("");
  const [baseline, setBaseline] = useState("");
  const [assessmentPlanTitle, setAssessmentPlanTitle] = useState("");
  const [assessmentPlanDescription, setAssessmentPlanDescription] = useState("");
  const [assessmentSspVersion, setAssessmentSspVersion] = useState("");
  const [systemIds, setSystemIds] = useState(system.system_ids);
  const [informationTypes, setInformationTypes] = useState<Array<{ uuid?: string; title: string; description: string }>>(system.information_types);

  function upsertById<T extends { id: string }>(items: T[], next: T): T[] {
    const index = items.findIndex((item) => item.id === next.id);
    if (index === -1) return [...items, next];
    return items.map((item, itemIndex) => (itemIndex === index ? next : item));
  }

  async function saveSystem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const result = await request<InformationSystem>(
        `/bff/tenants/${tenantId}/systems/${system.id}`,
        "PUT",
        {
          name: system.name,
          description: system.description,
          system_boundary: system.system_boundary,
          system_ids: systemIds.map((item) => ({ id: item.id, identifier_type: item["identifier-type"] || null })),
          information_types: informationTypes,
          operational_status: system.operational_status,
          status_remarks: system.status_remarks,
          security_sensitivity_level: system.security_sensitivity_level,
        },
        t,
        errorMessage,
      );
      setSystem(result);
      setSystemIds(result.system_ids);
      setInformationTypes(result.information_types);
      return t("systems.characteristicsSaved");
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
        t,
        errorMessage,
      );
      setComponents((current) => upsertById(current, result));
      resetComponentForm();
      setComponentForm(false);
      return editingComponent ? t("systems.systemComponentUpdated") : t("systems.systemComponentAdded");
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
        t,
        errorMessage,
      );
      setPlans((current) => upsertById(current, result));
      setPlanTitle("");
      setControlDescription("");
      setPlanForm(false);
      return t("systems.sspDraftCreated");
    });
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setNotice(await action());
    } catch (reason) {
      setError(reason instanceof Error ? errorMessage(reason) : t("systems.requestFailed"));
    } finally {
      setBusy(false);
    }
  }

  async function createAssessmentPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assessmentSspVersion) return;
    await run(async () => {
      const result = await request<AssessmentPlan>(
        `/bff/tenants/${tenantId}/systems/${system.id}/assessment-plans`,
        "POST",
        {
          ssp_version_id: assessmentSspVersion,
          title: assessmentPlanTitle,
          description: assessmentPlanDescription || null,
        },
        t,
        errorMessage,
      );
      setAssessmentPlans((current) => upsertById(current, result));
      setAssessmentPlanTitle("");
      setAssessmentPlanDescription("");
      setAssessmentSspVersion("");
      setAssessmentPlanForm(false);
      return t("assessmentPlans.created");
    });
  }

  function chooseReusableComponent(value: string) {
    setSourceSelection(value);
    const [documentId, componentId] = value.split("|");
    const source = definitions
      .find((definition) => definition.id === documentId)
      ?.components.find((item) => item.id === componentId);
    if (source) {
      setTitle(source.title);
      setDescription("");
    }
  }

  function serializeComponentDraft(next?: {
    componentType?: string;
    editingComponent?: string | null;
    sourceSelection?: string;
    adopting?: boolean;
    title?: string;
    description?: string;
    purpose?: string;
    componentStatus?: string;
    componentRemarks?: string;
  }): string {
    return JSON.stringify({
      componentType: next?.componentType ?? componentType,
      editingComponent: next?.editingComponent ?? editingComponent,
      sourceSelection: next?.sourceSelection ?? sourceSelection,
      adopting: next?.adopting ?? adopting,
      title: next?.title ?? title,
      description: next?.description ?? description,
      purpose: next?.purpose ?? purpose,
      componentStatus: next?.componentStatus ?? componentStatus,
      componentRemarks: next?.componentRemarks ?? componentRemarks,
    });
  }

  function resetComponentForm() {
    setComponentType("service");
    setEditingComponent(null);
    setAdopting(false);
    setSourceSelection("");
    setTitle("");
    setDescription("");
    setPurpose("");
    setComponentStatus("");
    setComponentRemarks("");
    setComponentDraftBaseline(EMPTY_COMPONENT_DRAFT);
  }

  function openComponentForm(mode: "new" | "adopt" | SystemComponent) {
    const same = mode === "new" ? !editingComponent && !adopting : mode === "adopt" ? adopting : editingComponent === mode.id;
    const hasDraft = serializeComponentDraft() !== componentDraftBaseline;
    if (!same && hasDraft && !window.confirm(t("systems.discardComponentDraftConfirm"))) return;
    if (!same) {
      if (mode === "new") {
        const next = {
          componentType: "service",
          editingComponent: null,
          sourceSelection: "",
          adopting: false,
          title: "",
          description: "",
          purpose: "",
          componentStatus: "",
          componentRemarks: "",
        };
        setComponentType(next.componentType);
        setEditingComponent(next.editingComponent);
        setSourceSelection(next.sourceSelection);
        setAdopting(next.adopting);
        setTitle(next.title);
        setDescription(next.description);
        setPurpose(next.purpose);
        setComponentStatus(next.componentStatus);
        setComponentRemarks(next.componentRemarks);
        setComponentDraftBaseline(serializeComponentDraft(next));
      } else if (mode === "adopt") {
        const next = {
          componentType: "service",
          editingComponent: null,
          sourceSelection: "",
          adopting: true,
          title: "",
          description: "",
          purpose: "",
          componentStatus: "",
          componentRemarks: "",
        };
        setComponentType(next.componentType);
        setEditingComponent(next.editingComponent);
        setSourceSelection(next.sourceSelection);
        setAdopting(next.adopting);
        setTitle(next.title);
        setDescription(next.description);
        setPurpose(next.purpose);
        setComponentStatus(next.componentStatus);
        setComponentRemarks(next.componentRemarks);
        setComponentDraftBaseline(serializeComponentDraft(next));
      } else {
        const next = {
          componentType: "service",
          editingComponent: mode.id,
          sourceSelection: "",
          adopting: false,
          title: mode.component.title,
          description: mode.component.description,
          purpose: mode.component.purpose ?? "",
          componentStatus: mode.component.status.state,
          componentRemarks: mode.component.status.remarks ?? "",
        };
        setComponentType(next.componentType);
        setEditingComponent(next.editingComponent);
        setSourceSelection(next.sourceSelection);
        setAdopting(next.adopting);
        setTitle(next.title);
        setDescription(next.description);
        setPurpose(next.purpose);
        setComponentStatus(next.componentStatus);
        setComponentRemarks(next.componentRemarks);
        setComponentDraftBaseline(serializeComponentDraft(next));
      }
    }
    setComponentForm(true);
  }

  function closeComponentForm() {
    const hasDraft = serializeComponentDraft() !== componentDraftBaseline;
    if (hasDraft) {
      if (!window.confirm(t("systems.discardComponentDraftConfirm"))) return;
      resetComponentForm();
    }
    setComponentForm(false);
  }

  const selectedSource = sourceSelection.split("|");
  const selectedDefinition = definitions.find((definition) => definition.id === selectedSource[0]);
  const sourceReferenceByOscalUuid = new Map(
    definitions.flatMap((definition) =>
      definition.components.map((source) => [source.oscal_uuid, { definitionTitle: definition.title, componentTitle: source.title }] as const),
    ),
  );
  const availableRevisions = revisions.filter(
    (item) => item.revision.lifecycle_status !== "withdrawn",
  );
  const availableSspVersions = plans.flatMap((plan) =>
    (initialVersions[plan.id] ?? []).map((version) => ({
      plan,
      version,
      revision: planRevisions[plan.id],
    })),
  );
  const sspVersionById = new Map(availableSspVersions.map(({ version, plan, revision }) => [
    version.id,
    { version, plan, revision },
  ] as const));
  const assessmentPlansBySspPlanId = new Map<string, AssessmentPlan[]>();
  assessmentPlans.forEach((assessmentPlan) => {
    const linked = sspVersionById.get(assessmentPlan.system_security_plan_version_id);
    if (!linked) return;
    const current = assessmentPlansBySspPlanId.get(linked.plan.id) ?? [];
    current.push(assessmentPlan);
    assessmentPlansBySspPlanId.set(linked.plan.id, current);
  });
  const assessmentPlanById = new Map(assessmentPlans.map((item) => [item.id, item] as const));
  const assessmentResultsByPlanId = new Map<string, AssessmentResult[]>();
  assessmentResults.forEach((result) => {
    const current = assessmentResultsByPlanId.get(result.assessment_plan_id) ?? [];
    current.push(result);
    assessmentResultsByPlanId.set(result.assessment_plan_id, current);
  });
  const sspVersionLabelById = Object.fromEntries(
    availableSspVersions.map(({ plan, version }) => [
      version.id,
      `${plan.title} · ${version.document_version}`,
    ]),
  );

  return (
    <div className="workspace system-workspace">
      <a href={`/t/${tenantId}/systems`}>{t("systems.backToSystems")}</a>
      <h1>{system.name}</h1>
      <p className="muted">
        {t("systems.sharedSystemFacts")}
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      <nav className="workspace-tabs" aria-label={t("systems.systemSections")}>
        {([["overview", t("systems.overview")], ["components", t("systems.components")], ["plans", t("systems.securityPlans")]] as const).map(([id, label]) => (
          <button type="button" key={id} aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>{label}</button>
        ))}
      </nav>

      <section className="panel" hidden={tab !== "overview"}>
        <h2>{t("systems.systemCharacteristics")}</h2>
        <form className="stack" onSubmit={saveSystem}>
          <label className="field">
            {t("systems.systemName")}
            <input
              value={system.name}
              maxLength={255}
              onChange={(event) => setSystem({ ...system, name: event.target.value })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            {t("systems.systemDescription")}
            <textarea
              value={system.description ?? ""}
              onChange={(event) => setSystem({ ...system, description: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            {t("systems.authorizationBoundaryDescription")}
            <textarea
              value={system.system_boundary ?? ""}
              onChange={(event) => setSystem({ ...system, system_boundary: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          <fieldset className="repeatable-fields">
            <legend>{t("systems.systemIdentifiers")}</legend>
            {systemIds.map((item, index) => (
              <div className="repeatable-row" key={index}>
                <label className="field">{t("systems.identifier")}<input required value={item.id} disabled={!canWrite || busy} onChange={(event) => setSystemIds(systemIds.map((row, i) => i === index ? { ...row, id: event.target.value } : row))} /></label>
                <label className="field">{t("systems.identifierTypeOptional")}<input value={item["identifier-type"] ?? ""} disabled={!canWrite || busy} onChange={(event) => setSystemIds(systemIds.map((row, i) => i === index ? { ...row, "identifier-type": event.target.value } : row))} /></label>
                {canWrite ? <button type="button" className="secondary" onClick={() => setSystemIds(systemIds.filter((_, i) => i !== index))}>{t("systems.removeIdentifier")}</button> : null}
              </div>
            ))}
            {canWrite ? <button type="button" className="secondary" onClick={() => setSystemIds([...systemIds, { id: "" }])}>{t("systems.addIdentifier")}</button> : null}
          </fieldset>
          <fieldset className="repeatable-fields">
            <legend>{t("systems.informationTypes")}</legend>
            {informationTypes.map((item, index) => (
              <div className="repeatable-row" key={index}>
                <label className="field">{t("systems.title")}<input required value={item.title} disabled={!canWrite || busy} onChange={(event) => setInformationTypes(informationTypes.map((row, i) => i === index ? { ...row, title: event.target.value } : row))} /></label>
                <label className="field">{t("systems.description")}<textarea required value={item.description} disabled={!canWrite || busy} onChange={(event) => setInformationTypes(informationTypes.map((row, i) => i === index ? { ...row, description: event.target.value } : row))} /></label>
                {canWrite ? <button type="button" className="secondary" onClick={() => setInformationTypes(informationTypes.filter((_, i) => i !== index))}>{t("systems.removeInformationType")}</button> : null}
              </div>
            ))}
            {canWrite ? <button type="button" className="secondary" onClick={() => setInformationTypes([...informationTypes, { title: "", description: "" }])}>{t("systems.addInformationType")}</button> : null}
          </fieldset>
          <label className="field">
            {t("systems.oscalOperationalStatus")}
            <select
              value={system.operational_status ?? ""}
              onChange={(event) => setSystem({ ...system, operational_status: event.target.value || null })}
              disabled={!canWrite || busy}
            >
              <option value="">{t("systems.notSet")}</option>
              <option value="operational">{enumLabel("operational")}</option>
              <option value="under-development">{enumLabel("under-development")}</option>
              <option value="under-major-modification">{enumLabel("under-major-modification")}</option>
              <option value="disposition">{enumLabel("disposition")}</option>
              <option value="other">{enumLabel("other")}</option>
            </select>
          </label>
          {system.operational_status === "other" ? (
            <label className="field">
              {t("systems.explainOtherStatus")}
              <textarea
                value={system.status_remarks ?? ""}
                onChange={(event) => setSystem({ ...system, status_remarks: event.target.value || null })}
                disabled={!canWrite || busy}
              />
            </label>
          ) : null}
          <label className="field">
            {t("systems.securitySensitivityLevel")}
            <input
              value={system.security_sensitivity_level ?? ""}
              onChange={(event) => setSystem({ ...system, security_sensitivity_level: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          {canWrite ? <button disabled={busy}>{t("systems.saveSystemCharacteristics")}</button> : null}
        </form>
      </section>

      <section className="panel" hidden={tab !== "components"}>
        <h2>{t("systems.concreteSystemComponents")}</h2>
        <p className="muted">{t("systems.actualComponentsGuidance")}</p>
        <div className="workspace-actions system-components-toolbar">
          {canWrite ? <>
            <button type="button" onClick={() => openComponentForm("new")}>{t("systems.addComponent")}</button>
            <button type="button" className="secondary" disabled={!definitions.some((item) => item.components.length)} onClick={() => openComponentForm("adopt")}>{t("systems.adoptReusableMeasure")}</button>
          </> : null}
        </div>
        <div className={`system-components-layout${componentForm && canWrite ? " has-editor" : ""}`}>
          <div>
            {components.length ? (
              <ul className="system-component-grid">
                {components.map((item) => {
                  const sourceReference = item.source_component_uuid ? sourceReferenceByOscalUuid.get(item.source_component_uuid) : null;
                  const sourceHref =
                    item.source_snapshot_id && item.source_component_uuid
                      ? `/t/${tenantId}/systems/${system.id}/components/${item.id}/source-snapshot`
                      : null;
                  return (
                    <li key={item.id} className="card system-component-card">
                      <div className="system-component-title-row">
                        <strong>{item.component.title}</strong>
                        <span className={item.source_snapshot_id ? "badge badge-warn" : "badge"}>
                          {item.source_snapshot_id ? t("systems.adoptedComponent") : t("systems.nativeComponent")}
                        </span>
                      </div>
                      <p>{item.component.description}</p>
                      <dl className="meta-list">
                        <dt>{t("systems.componentType")}</dt>
                        <dd>{item.component.type === "process-procedure" ? t("systems.processProcedure") : enumLabel(item.component.type)}</dd>
                        <dt>{t("systems.componentOperationalStatus")}</dt>
                        <dd>{enumLabel(item.component.status.state)}</dd>
                        {item.is_system_component ? <>
                          <dt>{t("systems.scope")}</dt>
                          <dd>{t("systems.thisSystem")}</dd>
                        </> : null}
                      </dl>
                      {item.source_snapshot_id ? <p className="muted">{t("systems.adoptedImmutableSnapshot")}</p> : null}
                      {sourceReference ? (
                        <p className="muted">{t("systems.adoptionSource", { definition: sourceReference.definitionTitle, component: sourceReference.componentTitle })}</p>
                      ) : item.source_snapshot_id ? (
                        <p className="muted">{t("systems.adoptionSourceUnavailable")}</p>
                      ) : null}
                      <div className="workspace-actions system-component-actions">
                        {sourceHref ? <a className="button secondary" href={sourceHref}>{t("systems.viewSourceSnapshot")}</a> : null}
                        {canWrite ? (
                          <button className="secondary" type="button" onClick={() => openComponentForm(item)}>
                            {t("systems.editComponent")}
                          </button>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : <p className="muted">{t("systems.noConcreteComponents")}</p>}
          </div>
          {canWrite && componentForm ? (
            <aside className="panel system-component-editor" aria-live="polite">
              <form className="stack" onSubmit={saveComponent}>
                <h3>{editingComponent ? t("systems.editComponent") : adopting ? t("systems.adoptReusableComponent") : t("systems.addConcreteComponent")}</h3>
                {!editingComponent && !adopting ? (
                  <label className="field">
                    {t("systems.componentType")}
                    <select value={componentType} onChange={(event) => setComponentType(event.target.value)}>
                      <option value="service">{enumLabel("service")}</option>
                      <option value="software">{enumLabel("software")}</option>
                      <option value="hardware">{enumLabel("hardware")}</option>
                      <option value="system">{enumLabel("system")}</option>
                      <option value="interconnection">{enumLabel("interconnection")}</option>
                      <option value="policy">{enumLabel("policy")}</option>
                      <option value="physical">{enumLabel("physical")}</option>
                      <option value="process-procedure">{t("systems.processProcedure")}</option>
                      <option value="this-system">{t("systems.thisSystemContributions")}</option>
                    </select>
                  </label>
                ) : null}
                {adopting ? (
                  <label className="field">
                    {t("systems.reusableDefinitionComponent")}
                    <select
                      required
                      value={sourceSelection}
                      onChange={(event) => chooseReusableComponent(event.target.value)}
                    >
                      <option value="">{t("systems.selectSourceComponent")}</option>
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
                    {t("systems.sourceSnapshot", { name: selectedDefinition.title })}
                  </p>
                ) : null}
                <label className="field">
                  {t("systems.componentTitle")}
                  <input required value={title} onChange={(event) => setTitle(event.target.value)} />
                </label>
                <label className="field">
                  {t("systems.actualDeploymentDescription")}
                  <textarea required value={description} onChange={(event) => setDescription(event.target.value)} />
                </label>
                <label className="field">
                  {t("systems.purposeOptional")}
                  <input value={purpose} onChange={(event) => setPurpose(event.target.value)} />
                </label>
                <label className="field">
                  {t("systems.componentOperationalStatus")}
                  <select required value={componentStatus} onChange={(event) => setComponentStatus(event.target.value)}>
                    <option value="">{t("systems.selectStatus")}</option>
                    <option value="operational">{enumLabel("operational")}</option>
                    <option value="under-development">{enumLabel("under-development")}</option>
                    <option value="disposition">{enumLabel("disposition")}</option>
                    <option value="other">{enumLabel("other")}</option>
                  </select>
                </label>
                {componentStatus === "other" ? (
                  <label className="field">
                    {t("systems.explainOtherStatus")}
                    <textarea value={componentRemarks} onChange={(event) => setComponentRemarks(event.target.value)} />
                  </label>
                ) : null}
                <div className="workspace-actions">
                  <button disabled={busy || (adopting && !sourceSelection)}>
                    {busy ? t("systems.saving") : editingComponent ? t("systems.saveComponent") : adopting ? t("systems.adoptComponent") : t("systems.addComponent")}
                  </button>
                  <button className="secondary" type="button" onClick={closeComponentForm}>{t("systems.cancel")}</button>
                  <button className="secondary" type="button" onClick={() => { resetComponentForm(); setComponentForm(false); }}>{t("systems.discardDraft")}</button>
                </div>
              </form>
            </aside>
          ) : null}
        </div>
      </section>

      <section className="panel" hidden={tab !== "plans"}>
        <h2>{t("systems.securityPlans")}</h2>
        <p className="muted">{t("systems.baselineExplanation")}</p>
        {canWrite ? <button type="button" onClick={() => setPlanForm(true)}>{t("systems.newSsp")}</button> : null}
        {plans.length ? (
          <ul className="profile-list ssp-overview-cards">
            {plans.map((plan) => {
              const relatedPlans = (assessmentPlansBySspPlanId.get(plan.id) ?? []).sort((left, right) => left.title.localeCompare(right.title));
              const relatedResults = relatedPlans.flatMap((assessmentPlan) =>
                (assessmentResultsByPlanId.get(assessmentPlan.id) ?? []).map((result) => ({ assessmentPlan, result })),
              );
              return (
              <li key={plan.id} className="card ssp-overview-card">
                <h3>{plan.title}</h3>
                <p>
                  {plan.catalog_name} · {t("systems.pinnedRevision", { revision: number(planRevisions[plan.id]?.revision_number ?? revisions.find((item) => item.revision.id === plan.revision_id)?.revision.revision_number ?? 0) })}
                </p>
                <p className="muted">{t("systems.immutableVersions", { count: number(initialVersions[plan.id]?.length ?? 0) })}{initialVersions[plan.id]?.length ? ` · ${initialVersions[plan.id].map((version) => version.document_version).join(", ")}` : ""}</p>
                <p className="muted">
                  {t("systems.documentedControls", { documented: number(plan.documented_control_count), baseline: number(plan.baseline_control_count) })}
                </p>
                <section>
                  <h4>{t("assessmentPlans.sectionTitle")}</h4>
                  {relatedPlans.length ? (
                    <ul className="profile-list">
                      {relatedPlans.map((assessmentPlan) => {
                        const linkedVersion = sspVersionById.get(assessmentPlan.system_security_plan_version_id);
                        return (
                        <li key={assessmentPlan.id}>
                          <strong>{assessmentPlan.title}</strong>
                          <p className="muted">
                            {t("assessmentPlans.pinnedSspVersion", {
                              version: linkedVersion
                                ? `${linkedVersion.plan.title} · ${linkedVersion.version.document_version}`
                                : assessmentPlan.system_security_plan_version_id,
                            })}
                          </p>
                          <a
                            className="button secondary"
                            href={`/t/${tenantId}/systems/${system.id}/assessment-plans/${assessmentPlan.id}`}
                          >
                            {t("assessmentPlans.openPlan")}
                          </a>
                        </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="muted">{t("assessmentPlans.noPlans")}</p>
                  )}
                </section>
                <section>
                  <h4>{t("assessmentResults.sectionTitle")}</h4>
                  {relatedResults.length ? (
                    <ul className="profile-list">
                      {relatedResults.map(({ assessmentPlan, result }) => (
                        <li key={result.id}>
                          <strong>{result.title}</strong>
                          <p className="muted">
                            {t("systems.assessmentResultRelationship", {
                              plan: assessmentPlan.title,
                              reference: result.assessment_plan_version_id,
                            })}
                          </p>
                          <a className="button secondary" href={`/t/${tenantId}/systems/${system.id}/assessment-results/${result.id}`}>
                            {t("assessmentResults.openResult")}
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted">{t("assessmentResults.noResultsWorkspace")}</p>
                  )}
                </section>
                <a className="button" href={`/t/${tenantId}/systems/${system.id}/system-security-plans/${plan.id}`}>
                  {t("systems.openSspWorkingState")}
                </a>
              </li>
              );
            })}
          </ul>
        ) : <p className="muted">{t("systems.noSspDrafts")}</p>}
        {canWrite && planForm ? (
          <form className="stack" onSubmit={createPlan}>
            <h3>{t("systems.createSspDraft")}</h3>
            <label className="field">
              {t("systems.pinnedCatalogRevision")}
              <select required value={baseline} onChange={(event) => setBaseline(event.target.value)}>
                <option value="">{t("systems.selectCatalogRevision")}</option>
                {availableRevisions.map(({ catalog, revision }) => (
                  <option key={`${catalog.id}|${revision.id}`} value={`${catalog.id}|${revision.id}`}>
                    {catalog.name} · {t("systems.pinnedRevision", { revision: number(revision.revision_number) })}{revision.source_version ? ` · ${t("systems.version", { version: revision.source_version })}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("systems.sspTitle")}
              <input required value={planTitle} onChange={(event) => setPlanTitle(event.target.value)} />
            </label>
            <label className="field">
              {t("systems.controlImplementationDescription")}
              <textarea
                value={controlDescription}
                onChange={(event) => setControlDescription(event.target.value)}
                placeholder={t("systems.controlDescriptionPlaceholder")}
              />
            </label>
            <button disabled={busy || !baseline}>{t("systems.createSspDraft")}</button>
            <button type="button" className="secondary" onClick={() => setPlanForm(false)}>{t("systems.close")}</button>
          </form>
        ) : null}
        {catalogs.length === 0 ? <p className="muted">{t("systems.importCatalogFirst")}</p> : null}

        <h3>{t("assessmentPlans.sectionTitle")}</h3>
        <p className="muted">{t("assessmentPlans.sectionIntro")}</p>
        {canWrite ? (
          <button type="button" className="secondary" onClick={() => setAssessmentPlanForm(true)}>
            {t("assessmentPlans.newPlan")}
          </button>
        ) : null}
        {assessmentPlans.length ? (
          <ul className="profile-list">
            {assessmentPlans.map((plan) => (
              <li key={plan.id}>
                <h4>{plan.title}</h4>
                <p className="muted">
                  {t("assessmentPlans.pinnedSspVersion", {
                    version:
                      sspVersionLabelById[plan.system_security_plan_version_id] ??
                      plan.system_security_plan_version_id,
                  })}
                </p>
                <a
                  className="button"
                  href={`/t/${tenantId}/systems/${system.id}/assessment-plans/${plan.id}`}
                >
                  {t("assessmentPlans.openPlan")}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("assessmentPlans.noPlans")}</p>
        )}
        {canWrite && assessmentPlanForm ? (
          <form className="stack" onSubmit={createAssessmentPlan}>
            <h4>{t("assessmentPlans.createTitle")}</h4>
            <label className="field">
              {t("assessmentPlans.sspVersion")}
              <select
                required
                value={assessmentSspVersion}
                onChange={(event) => setAssessmentSspVersion(event.target.value)}
              >
                <option value="">{t("assessmentPlans.selectSspVersion")}</option>
                {availableSspVersions.map(({ plan, version, revision }) => (
                  <option key={version.id} value={version.id}>
                    {plan.title} · {version.document_version}
                    {revision ? ` · ${t("systems.pinnedRevision", { revision: number(revision.revision_number) })}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t("assessmentPlans.title")}
              <input
                required
                value={assessmentPlanTitle}
                onChange={(event) => setAssessmentPlanTitle(event.target.value)}
              />
            </label>
            <label className="field">
              {t("assessmentPlans.description")}
              <textarea
                value={assessmentPlanDescription}
                onChange={(event) => setAssessmentPlanDescription(event.target.value)}
              />
            </label>
            <button disabled={busy || !assessmentSspVersion}>{t("assessmentPlans.createAction")}</button>
            <button type="button" className="secondary" onClick={() => setAssessmentPlanForm(false)}>
              {t("systems.close")}
            </button>
          </form>
        ) : null}

        <h3>{t("assessmentResults.sectionTitle")}</h3>
        <p className="muted">{t("assessmentResults.workspaceIntro")}</p>
        {assessmentResults.length ? (
          <ul className="profile-list">
            {assessmentResults.map((item) => (
              <li key={item.id}>
                <h4>{item.title}</h4>
                <p className="muted">
                  {t("assessmentResults.planVersion")}: {assessmentPlanById.get(item.assessment_plan_id)?.title ?? item.assessment_plan_id} · {item.assessment_plan_version_id}
                </p>
                <p className="muted">
                  {t("assessmentResults.scopeSummary", {
                    controls: number(item.reviewed_control_ids.length),
                    observations: number(item.observations.length),
                    findings: number(item.findings.length),
                  })}
                </p>
                <a className="button" href={`/t/${tenantId}/systems/${system.id}/assessment-results/${item.id}`}>
                  {t("assessmentResults.openResult")}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("assessmentResults.noResultsWorkspace")}</p>
        )}
      </section>
    </div>
  );
}

async function request<T>(
  path: string,
  method: "POST" | "PUT",
  body: unknown,
  t: Translate,
  errorMessage: (error: unknown) => string,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result: unknown = response.status === 204 ? null : await response.json();
  if (!response.ok) throw new Error(readError(result, t, errorMessage));
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
