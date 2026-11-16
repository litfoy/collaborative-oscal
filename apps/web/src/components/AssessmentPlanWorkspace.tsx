"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";

import { MappingControlPicker } from "@/components/MappingControlPicker";
import { bffGet, bffWrite } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
import type {
  AssessmentActivity,
  AssessmentActivityStep,
  AssessmentLocalObjective,
  AssessmentMethod,
  AssessmentParty,
  AssessmentPlan,
  AssessmentPlanValidation,
  AssessmentPlanVersion,
  AssessmentRole,
  AssessmentSourceObjective,
  AssessmentTask,
  InformationSystem,
  RevisionSummary,
  SystemSecurityPlan,
  SystemSecurityPlanVersion,
} from "@/lib/types";

const METHODS: AssessmentMethod[] = ["EXAMINE", "INTERVIEW", "TEST"];

type Tab = "overview" | "scope" | "activities" | "tasks" | "validation";

interface SubjectOption {
  uuid: string;
  title: string;
  type: string;
  description: string;
  status: string | null;
  remarks: string | null;
}

export function AssessmentPlanWorkspace({
  tenantId,
  system,
  initialPlan,
  initialValidation,
  initialVersions,
  ssp,
  sspVersion,
  revision,
  subjectOptions,
  canWrite,
}: {
  tenantId: string;
  system: InformationSystem;
  initialPlan: AssessmentPlan;
  initialValidation: AssessmentPlanValidation;
  initialVersions: AssessmentPlanVersion[];
  ssp: SystemSecurityPlan;
  sspVersion: SystemSecurityPlanVersion | null;
  revision: RevisionSummary | null;
  subjectOptions: SubjectOption[];
  canWrite: boolean;
}) {
  const { t, date, number, enumLabel, errorMessage } = useI18n();
  const [plan, setPlan] = useState(initialPlan);
  const [savedPlan, setSavedPlan] = useState(initialPlan);
  const [validation, setValidation] = useState(initialValidation);
  const [validationStale, setValidationStale] = useState(false);
  const [versions, setVersions] = useState(initialVersions);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [controlTitles, setControlTitles] = useState<Record<string, string>>({});

  const [editingLocalObjective, setEditingLocalObjective] = useState<number | null>(null);
  const [localObjectiveDraft, setLocalObjectiveDraft] =
    useState<AssessmentLocalObjective | null>(null);
  const [editingActivity, setEditingActivity] = useState<number | null>(null);
  const [activityDraft, setActivityDraft] = useState<AssessmentActivity | null>(null);
  const [editingTask, setEditingTask] = useState<number | null>(null);
  const [taskDraft, setTaskDraft] = useState<AssessmentTask | null>(null);
  const [editingRole, setEditingRole] = useState<number | null>(null);
  const [roleDraft, setRoleDraft] = useState<AssessmentRole | null>(null);
  const [editingParty, setEditingParty] = useState<number | null>(null);
  const [partyDraft, setPartyDraft] = useState<AssessmentParty | null>(null);

  const dirty = useMemo(
    () => JSON.stringify(planSnapshot(plan)) !== JSON.stringify(planSnapshot(savedPlan)),
    [plan, savedPlan],
  );
  const selectedSubjectSet = useMemo(() => new Set(plan.subject_uuids), [plan.subject_uuids]);
  const sourceObjectivesById = useMemo(
    () => new Map(validation.source_objectives.map((item) => [item.objective_id, item])),
    [validation.source_objectives],
  );

  useEffect(() => {
    if (!dirty && !busy) return;
    const unload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (
        !link ||
        link.getAttribute("href")?.startsWith("#") ||
        link.getAttribute("target") === "_blank" ||
        link.hasAttribute("download") ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        event.altKey ||
        event.button !== 0
      ) {
        return;
      }
      if (busy || !window.confirm(t("register.discardChangesConfirm"))) {
        event.preventDefault();
      }
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", navigate, true);
    };
  }, [dirty, busy, t]);

  function updatePlan(next: AssessmentPlan) {
    setPlan(next);
    setValidationStale(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const updated = await bffWrite<AssessmentPlan>(
        "PUT",
        `tenants/${tenantId}/assessment-plans/${plan.id}`,
        {
          title: plan.title,
          description: plan.description,
          control_ids: plan.control_ids,
          source_objectives: plan.source_objectives,
          local_objectives: plan.local_objectives,
          subject_uuids: plan.subject_uuids,
          activities: plan.activities,
          tasks: plan.tasks,
          roles: plan.roles,
          parties: plan.parties,
          terms: plan.terms,
        },
      );
      setPlan(updated);
      setSavedPlan(updated);
      setValidationStale(true);
      return t("assessmentPlans.saved");
    });
  }

  async function validatePlan() {
    if (dirty) {
      setNotice(t("assessmentPlans.validationSaveFirst"));
      return;
    }
    await run(async () => {
      const result = await bffGet<AssessmentPlanValidation>(
        `tenants/${tenantId}/assessment-plans/${plan.id}/validation`,
      );
      setValidation(result);
      setValidationStale(false);
      return result.valid
        ? t("assessmentPlans.validationPassed")
        : t("assessmentPlans.validationIssues");
    });
  }

  async function createVersion() {
    await run(async () => {
      const version = await bffWrite<AssessmentPlanVersion>(
        "POST",
        `tenants/${tenantId}/assessment-plans/${plan.id}/versions`,
        {},
      );
      setVersions((current) => [
        version,
        ...current.filter((item) => item.id !== version.id),
      ]);
      return version.created
        ? t("assessmentPlans.versionCreated", { version: version.document_version })
        : t("assessmentPlans.versionUnchanged");
    });
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setNotice(await action());
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  function applyControlSelection(ids: string[]) {
    const removed = plan.control_ids.filter((id) => !ids.includes(id));
    if (removed.length === 0) {
      updatePlan({ ...plan, control_ids: ids });
      return;
    }
    const removedObjectives = new Set(
      [...plan.source_objectives, ...plan.local_objectives]
        .filter((item) => removed.includes(item.control_id))
        .map((item) => item.objective_id),
    );
    const hasDependencies =
      removedObjectives.size > 0 ||
      plan.activities.some(
        (item) =>
          item.control_ids.some((control) => removed.includes(control)) ||
          item.objective_ids.some((objective) => removedObjectives.has(objective)),
      );
    if (hasDependencies && !window.confirm(t("assessmentPlans.confirmScopeReduction"))) return;
    updatePlan({
      ...plan,
      control_ids: ids,
      source_objectives: plan.source_objectives.filter((item) => !removed.includes(item.control_id)),
      local_objectives: plan.local_objectives.filter((item) => !removed.includes(item.control_id)),
      activities: plan.activities.map((activity) => ({
        ...activity,
        control_ids: activity.control_ids.filter((control) => !removed.includes(control)),
        objective_ids: activity.objective_ids.filter((objective) => !removedObjectives.has(objective)),
      })),
    });
  }

  function toggleSubject(uuid: string, checked: boolean) {
    const next = checked
      ? [...plan.subject_uuids, uuid]
      : plan.subject_uuids.filter((item) => item !== uuid);
    updatePlan({
      ...plan,
      subject_uuids: next,
      tasks: plan.tasks.map((task) => ({
        ...task,
        subject_uuids: task.subject_uuids.filter((item) => next.includes(item)),
      })),
    });
  }

  function toggleSourceObjective(item: AssessmentSourceObjective, checked: boolean) {
    if (checked) {
      if (plan.source_objectives.some((current) => current.objective_id === item.objective_id)) return;
      updatePlan({ ...plan, source_objectives: [...plan.source_objectives, item] });
      return;
    }
    const inUse = plan.activities.some((activity) => activity.objective_ids.includes(item.objective_id));
    if (inUse && !window.confirm(t("assessmentPlans.confirmObjectiveRemoval"))) return;
    updatePlan({
      ...plan,
      source_objectives: plan.source_objectives.filter(
        (current) => current.objective_id !== item.objective_id,
      ),
      activities: plan.activities.map((activity) => ({
        ...activity,
        objective_ids: activity.objective_ids.filter((id) => id !== item.objective_id),
      })),
    });
  }

  function startLocalObjective(index: number | null) {
    if (index === null) {
      setEditingLocalObjective(null);
      setLocalObjectiveDraft({
        objective_id: nextLocalObjectiveId(plan.local_objectives, plan.control_ids[0] ?? "objective"),
        control_id: plan.control_ids[0] ?? "",
        description: "",
        methods: [],
      });
      return;
    }
    setEditingLocalObjective(index);
    setLocalObjectiveDraft({ ...plan.local_objectives[index] });
  }

  function saveLocalObjective() {
    if (!localObjectiveDraft) return;
    const conflict =
      plan.source_objectives.some(
        (item) => item.objective_id === localObjectiveDraft.objective_id,
      ) ||
      plan.local_objectives.some(
        (item, index) =>
          item.objective_id === localObjectiveDraft.objective_id && index !== editingLocalObjective,
      );
    if (conflict) {
      setError(t("assessmentPlans.localObjectiveConflict"));
      return;
    }
    const next = [...plan.local_objectives];
    if (editingLocalObjective === null) next.push(localObjectiveDraft);
    else next[editingLocalObjective] = localObjectiveDraft;
    updatePlan({ ...plan, local_objectives: next });
    setEditingLocalObjective(null);
    setLocalObjectiveDraft(null);
  }

  function removeLocalObjective(objectiveId: string) {
    const inUse = plan.activities.some((activity) => activity.objective_ids.includes(objectiveId));
    if (inUse && !window.confirm(t("assessmentPlans.confirmObjectiveRemoval"))) return;
    updatePlan({
      ...plan,
      local_objectives: plan.local_objectives.filter((item) => item.objective_id !== objectiveId),
      activities: plan.activities.map((activity) => ({
        ...activity,
        objective_ids: activity.objective_ids.filter((id) => id !== objectiveId),
      })),
    });
  }

  function startActivity(index: number | null) {
    if (index === null) {
      setEditingActivity(null);
      setActivityDraft({
        id: generateId(),
        title: "",
        description: "",
        methods: [],
        steps: [],
        control_ids: [],
        objective_ids: [],
        planned_evidence: null,
      });
      return;
    }
    setEditingActivity(index);
    setActivityDraft({ ...plan.activities[index], steps: [...plan.activities[index].steps] });
  }

  function saveActivity() {
    if (!activityDraft) return;
    const next = [...plan.activities];
    if (editingActivity === null) next.push(activityDraft);
    else next[editingActivity] = activityDraft;
    updatePlan({ ...plan, activities: next });
    setEditingActivity(null);
    setActivityDraft(null);
  }

  function removeActivity(activityId: string) {
    const referenced = plan.tasks.some((task) => task.activity_ids.includes(activityId));
    if (referenced && !window.confirm(t("assessmentPlans.confirmTaskReferenceRemoval"))) return;
    updatePlan({
      ...plan,
      activities: plan.activities.filter((item) => item.id !== activityId),
      tasks: plan.tasks.map((task) => ({
        ...task,
        activity_ids: task.activity_ids.filter((id) => id !== activityId),
      })),
    });
  }

  function startTask(index: number | null) {
    if (index === null) {
      setEditingTask(null);
      setTaskDraft({
        id: generateId(),
        title: "",
        description: null,
        activity_ids: [],
        subject_uuids: [],
        role_ids: [],
        on_date: null,
        start: null,
        end: null,
      });
      return;
    }
    setEditingTask(index);
    setTaskDraft({ ...plan.tasks[index] });
  }

  function saveTask() {
    if (!taskDraft) return;
    const next = [...plan.tasks];
    if (editingTask === null) next.push(taskDraft);
    else next[editingTask] = taskDraft;
    updatePlan({ ...plan, tasks: next });
    setEditingTask(null);
    setTaskDraft(null);
  }

  function startRole(index: number | null) {
    if (index === null) {
      setEditingRole(null);
      setRoleDraft({ role_id: `role-${plan.roles.length + 1}`, title: "", description: null, party_uuids: [] });
      return;
    }
    setEditingRole(index);
    setRoleDraft({ ...plan.roles[index], party_uuids: [...plan.roles[index].party_uuids] });
  }

  function saveRole() {
    if (!roleDraft) return;
    const next = [...plan.roles];
    if (editingRole === null) next.push(roleDraft);
    else next[editingRole] = roleDraft;
    updatePlan({ ...plan, roles: next });
    setEditingRole(null);
    setRoleDraft(null);
  }

  function removeRole(roleId: string) {
    updatePlan({
      ...plan,
      roles: plan.roles.filter((role) => role.role_id !== roleId),
      tasks: plan.tasks.map((task) => ({
        ...task,
        role_ids: task.role_ids.filter((id) => id !== roleId),
      })),
    });
  }

  function startParty(index: number | null) {
    if (index === null) {
      setEditingParty(null);
      setPartyDraft({ uuid: generateId(), party_type: "person", name: "" });
      return;
    }
    setEditingParty(index);
    setPartyDraft({ ...plan.parties[index] });
  }

  function saveParty() {
    if (!partyDraft) return;
    const next = [...plan.parties];
    if (editingParty === null) next.push(partyDraft);
    else next[editingParty] = partyDraft;
    updatePlan({ ...plan, parties: next });
    setEditingParty(null);
    setPartyDraft(null);
  }

  function removeParty(uuid: string) {
    updatePlan({
      ...plan,
      parties: plan.parties.filter((party) => party.uuid !== uuid),
      roles: plan.roles.map((role) => ({
        ...role,
        party_uuids: role.party_uuids.filter((item) => item !== uuid),
      })),
    });
  }

  const allObjectiveIds = [
    ...plan.source_objectives.map((item) => item.objective_id),
    ...plan.local_objectives.map((item) => item.objective_id),
  ];

  return (
    <div className="workspace system-workspace">
      <a href={`/t/${tenantId}/systems/${system.id}`}>{t("assessmentPlans.backToSystem")}</a>
      <h1>{plan.title}</h1>
      <p className="muted">
        {t("assessmentPlans.systemReference")}: {system.name} · {t("assessmentPlans.sspReference")}: {ssp.title} · {t("assessmentPlans.pinnedVersion")}: {sspVersion?.document_version ?? plan.system_security_plan_version_id}
      </p>
      <p className="muted">
        {t("assessmentPlans.baselineReference")}: {ssp.catalog_name}
        {revision ? ` · ${t("common.revisionNumber", { number: number(revision.revision_number) })}` : ""}
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {dirty ? <p role="status">{t("systems.unsavedWorkingChanges")}</p> : null}
      {validationStale ? <p role="status">{t("assessmentPlans.validationOutdated")}</p> : null}

      <nav className="workspace-tabs" aria-label={t("assessmentPlans.sectionTitle")}>
        {([
          ["overview", t("assessmentPlans.overview")],
          ["scope", t("assessmentPlans.scope")],
          ["activities", t("assessmentPlans.activities")],
          ["tasks", t("assessmentPlans.tasks")],
          ["validation", t("assessmentPlans.validationVersions")],
        ] as const).map(([id, label]) => (
          <button key={id} type="button" aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>

      <form className="stack" onSubmit={save}>
        <section className="panel" hidden={tab !== "overview"}>
          <label className="field">
            {t("assessmentPlans.title")}
            <input value={plan.title} onChange={(event) => updatePlan({ ...plan, title: event.target.value })} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            {t("assessmentPlans.description")}
            <textarea value={plan.description ?? ""} onChange={(event) => updatePlan({ ...plan, description: event.target.value || null })} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            {t("assessmentPlans.terms")}
            <textarea value={plan.terms ?? ""} onChange={(event) => updatePlan({ ...plan, terms: event.target.value || null })} disabled={!canWrite || busy} />
          </label>
          <p className="muted">
            {t("assessmentPlans.requirementsCount")}: {number(plan.control_ids.length)} · {t("assessmentPlans.selectedSubjects", { count: number(plan.subject_uuids.length) })} · {t("assessmentPlans.activitiesCount")}: {number(plan.activities.length)} · {t("assessmentPlans.tasksCount")}: {number(plan.tasks.length)}
          </p>
        </section>

        <section className="panel" hidden={tab !== "scope"}>
          <h2>{t("assessmentPlans.scopeRequirements")}</h2>
          <MappingControlPicker
            tenantId={tenantId}
            catalogId={plan.baseline_catalog_id}
            revisionId={plan.baseline_revision_id}
            label={ssp.catalog_name}
            selected={plan.control_ids}
            onChange={applyControlSelection}
            onControlTitles={setControlTitles}
            disabled={!canWrite || busy}
          />
          <h2>{t("assessmentPlans.scopeSubjects")}</h2>
          {subjectOptions.length ? (
            <ul className="profile-list">
              {subjectOptions.map((subject) => (
                <li key={subject.uuid}>
                  <label className="requirement-select">
                    <input
                      type="checkbox"
                      checked={selectedSubjectSet.has(subject.uuid)}
                      disabled={!canWrite || busy}
                      onChange={(event) => toggleSubject(subject.uuid, event.target.checked)}
                    />
                    <span>
                      <strong>{subject.title}</strong> · {enumLabel(subject.type)}
                    </span>
                  </label>
                  <p>{subject.description}</p>
                  <p className="muted">
                    {subject.status ? enumLabel(subject.status) : t("common.notRecorded")}
                    {subject.remarks ? ` · ${subject.remarks}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("assessmentPlans.noSubjectsAvailable")}</p>
          )}

          <h2>{t("assessmentPlans.sourceObjectives")}</h2>
          {validation.source_objectives.length ? (
            <ul className="profile-list">
              {validation.source_objectives.map((item) => (
                <li key={item.objective_id}>
                  <label className="requirement-select">
                    <input
                      type="checkbox"
                      checked={plan.source_objectives.some((entry) => entry.objective_id === item.objective_id)}
                      disabled={!canWrite || busy}
                      onChange={(event) =>
                        toggleSourceObjective(
                          { objective_id: item.objective_id, control_id: item.control_id },
                          event.target.checked,
                        )
                      }
                    />
                    <span>
                      <strong>{item.title || item.objective_id}</strong> · {item.control_id}
                    </span>
                  </label>
                  {item.description ? <p>{item.description}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("assessmentPlans.noSourceObjectives")}</p>
          )}

          <h2>{t("assessmentPlans.localObjectives")}</h2>
          <div className="workspace-actions">
            <button type="button" disabled={!canWrite || busy || plan.control_ids.length === 0} onClick={() => startLocalObjective(null)}>
              {t("assessmentPlans.addLocalObjective")}
            </button>
          </div>
          {plan.local_objectives.length ? (
            <ul className="profile-list">
              {plan.local_objectives.map((objective, index) => (
                <li key={objective.objective_id}>
                  <strong>{objective.objective_id}</strong> · {objective.control_id}
                  <p>{objective.description}</p>
                  <p className="muted">
                    {objective.methods.map((method) => methodLabel(method, t as never)).join(", ") || t("common.none")}
                  </p>
                  <div className="workspace-actions">
                    <button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => startLocalObjective(index)}>{t("assessmentPlans.edit")}</button>
                    <button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => removeLocalObjective(objective.objective_id)}>{t("assessmentPlans.remove")}</button>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
          {localObjectiveDraft ? (
            <div className="panel stack">
              <h3>{editingLocalObjective === null ? t("assessmentPlans.addLocalObjective") : t("assessmentPlans.editLocalObjective")}</h3>
              <label className="field">{t("assessmentPlans.objectiveIdentifier")}<input value={localObjectiveDraft.objective_id} onChange={(event) => setLocalObjectiveDraft({ ...localObjectiveDraft, objective_id: event.target.value })} /></label>
              <label className="field">{t("assessmentPlans.objectiveForRequirement")}<select value={localObjectiveDraft.control_id} onChange={(event) => setLocalObjectiveDraft({ ...localObjectiveDraft, control_id: event.target.value })}>{plan.control_ids.map((id) => <option key={id} value={id}>{id}{controlTitles[id] ? ` - ${controlTitles[id]}` : ""}</option>)}</select></label>
              <label className="field">{t("assessmentPlans.objectiveDescription")}<textarea value={localObjectiveDraft.description} onChange={(event) => setLocalObjectiveDraft({ ...localObjectiveDraft, description: event.target.value })} /></label>
              <fieldset className="repeatable-fields"><legend>{t("assessmentPlans.objectiveMethods")}</legend>{METHODS.map((method) => <label key={method}><input type="checkbox" checked={localObjectiveDraft.methods.includes(method)} onChange={(event) => setLocalObjectiveDraft({ ...localObjectiveDraft, methods: event.target.checked ? [...localObjectiveDraft.methods, method] : localObjectiveDraft.methods.filter((item) => item !== method) })} /> {methodLabel(method, t)}</label>)}</fieldset>
              <div className="workspace-actions"><button type="button" onClick={saveLocalObjective}>{t("systems.saveWorkingState")}</button><button type="button" className="secondary" onClick={() => setLocalObjectiveDraft(null)}>{t("assessmentPlans.cancel")}</button></div>
            </div>
          ) : null}
        </section>

        <section className="panel" hidden={tab !== "activities"}>
          <div className="workspace-actions">
            <button type="button" disabled={!canWrite || busy} onClick={() => startActivity(null)}>{t("assessmentPlans.addActivity")}</button>
          </div>
          {plan.activities.length ? <ul className="profile-list">{plan.activities.map((activity, index) => <li key={activity.id}><strong>{activity.title}</strong><p>{activity.description}</p><p className="muted">{activity.methods.map((item) => methodLabel(item, t)).join(", ")}</p><div className="workspace-actions"><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => startActivity(index)}>{t("assessmentPlans.edit")}</button><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => removeActivity(activity.id)}>{t("assessmentPlans.remove")}</button></div></li>)}</ul> : <p className="muted">{t("assessmentPlans.noActivities")}</p>}
          {activityDraft ? <ActivityEditor draft={activityDraft} setDraft={setActivityDraft} canWrite={canWrite} busy={busy} controlIds={plan.control_ids} objectiveIds={allObjectiveIds} onSave={saveActivity} onCancel={() => setActivityDraft(null)} t={t} /> : null}
        </section>

        <section className="panel" hidden={tab !== "tasks"}>
          <h2>{t("assessmentPlans.tasks")}</h2>
          <div className="workspace-actions"><button type="button" disabled={!canWrite || busy} onClick={() => startTask(null)}>{t("assessmentPlans.addTask")}</button></div>
          {plan.tasks.length ? <ul className="profile-list">{plan.tasks.map((task, index) => <li key={task.id}><strong>{task.title}</strong><p>{task.description}</p><p className="muted">{task.activity_ids.length} {t("assessmentPlans.activities")} · {task.subject_uuids.length} {t("assessmentPlans.subjects")}</p><div className="workspace-actions"><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => startTask(index)}>{t("assessmentPlans.edit")}</button><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => updatePlan({ ...plan, tasks: plan.tasks.filter((item) => item.id !== task.id) })}>{t("assessmentPlans.remove")}</button></div></li>)}</ul> : <p className="muted">{t("assessmentPlans.noTasks")}</p>}
          {taskDraft ? <TaskEditor draft={taskDraft} setDraft={setTaskDraft} canWrite={canWrite} busy={busy} activities={plan.activities} selectedSubjects={subjectOptions.filter((item) => selectedSubjectSet.has(item.uuid))} roles={plan.roles} onSave={saveTask} onCancel={() => setTaskDraft(null)} t={t} /> : null}

          <h2>{t("assessmentPlans.rolesParties")}</h2>
          <div className="workspace-actions">
            <button type="button" disabled={!canWrite || busy} onClick={() => startRole(null)}>{t("assessmentPlans.addRole")}</button>
            <button type="button" disabled={!canWrite || busy} onClick={() => startParty(null)}>{t("assessmentPlans.addParty")}</button>
          </div>
          {plan.roles.length ? <ul className="profile-list">{plan.roles.map((role, index) => <li key={role.role_id}><strong>{role.title}</strong> · <span className="mono">{role.role_id}</span><p className="muted">{role.party_uuids.length} {t("assessmentPlans.subjects")}</p><div className="workspace-actions"><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => startRole(index)}>{t("assessmentPlans.edit")}</button><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => removeRole(role.role_id)}>{t("assessmentPlans.remove")}</button></div></li>)}</ul> : <p className="muted">{t("assessmentPlans.noRoles")}</p>}
          {plan.parties.length ? <ul className="profile-list">{plan.parties.map((party, index) => <li key={party.uuid}><strong>{party.name}</strong> · {party.party_type}<div className="workspace-actions"><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => startParty(index)}>{t("assessmentPlans.edit")}</button><button type="button" className="secondary" disabled={!canWrite || busy} onClick={() => removeParty(party.uuid)}>{t("assessmentPlans.remove")}</button></div></li>)}</ul> : <p className="muted">{t("assessmentPlans.noParties")}</p>}
          {roleDraft ? <RoleEditor draft={roleDraft} setDraft={setRoleDraft} parties={plan.parties} onSave={saveRole} onCancel={() => setRoleDraft(null)} t={t} /> : null}
          {partyDraft ? <PartyEditor draft={partyDraft} setDraft={setPartyDraft} onSave={saveParty} onCancel={() => setPartyDraft(null)} t={t} /> : null}
        </section>

        <section className="panel" hidden={tab !== "validation"}>
          <div className="workspace-actions">
            <button type="button" onClick={() => void validatePlan()} disabled={busy || dirty}>{t("assessmentPlans.validate")}</button>
            {canWrite ? <button type="button" onClick={() => void createVersion()} disabled={busy || dirty || validationStale || !validation.valid}>{t("assessmentPlans.createVersion")}</button> : null}
          </div>
          <p className="muted">{validation.valid ? t("assessmentPlans.validationPassed") : t("assessmentPlans.validationIssues")}</p>
          {validation.diagnostics.length ? <ul className="diagnostics">{validation.diagnostics.map((item, index) => <li key={`${item.code}:${index}`}><strong>{enumLabel(item.severity)}: {item.code}</strong> - {item.message}<p className="muted">{diagnosticGuidance(item.code, t)}</p></li>)}</ul> : <p>{t("assessmentPlans.noValidationDiagnostics")}</p>}
          <details>
            <summary>{t("assessmentPlans.oscalDetails")}</summary>
            <pre>{JSON.stringify(plan, null, 2)}</pre>
          </details>
          <h3>{t("systems.versions")}</h3>
          {versions.length ? <ul className="profile-list">{versions.map((version) => <li key={version.id}><strong>{t("common.version")} {version.document_version}</strong><p className="muted">OSCAL {version.oscal_version} · {date(version.created_at)}</p><a href={`/bff/tenants/${tenantId}/assessment-plans/${plan.id}/versions/${version.id}/export`}>{t("systems.exportStoredOscalJson")}</a></li>)}</ul> : <p className="muted">{t("systems.noImmutableVersions")}</p>}
        </section>

        {canWrite ? <button disabled={busy}>{t("assessmentPlans.save")}</button> : null}
      </form>
    </div>
  );
}

function ActivityEditor({
  draft,
  setDraft,
  canWrite,
  busy,
  controlIds,
  objectiveIds,
  onSave,
  onCancel,
  t,
}: {
  draft: AssessmentActivity;
  setDraft: (draft: AssessmentActivity) => void;
  canWrite: boolean;
  busy: boolean;
  controlIds: string[];
  objectiveIds: string[];
  onSave: () => void;
  onCancel: () => void;
  t: (key: never, values?: Record<string, string | number>) => string;
}) {
  return <div className="panel stack"><label className="field">{t("assessmentPlans.activityTitle" as never)}<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="field">{t("assessmentPlans.activityDescription" as never)}<textarea value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></label><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.activityMethods" as never)}</legend>{METHODS.map((method) => <label key={method}><input type="checkbox" checked={draft.methods.includes(method)} onChange={(event) => setDraft({ ...draft, methods: event.target.checked ? [...draft.methods, method] : draft.methods.filter((item) => item !== method) })} /> {methodLabel(method, t as never)}</label>)}</fieldset><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.scopeRequirements" as never)}</legend>{controlIds.map((id) => <label key={id}><input type="checkbox" checked={draft.control_ids.includes(id)} onChange={(event) => setDraft({ ...draft, control_ids: event.target.checked ? [...draft.control_ids, id] : draft.control_ids.filter((item) => item !== id) })} /> {id}</label>)}</fieldset><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.scopeObjectives" as never)}</legend>{objectiveIds.map((id) => <label key={id}><input type="checkbox" checked={draft.objective_ids.includes(id)} onChange={(event) => setDraft({ ...draft, objective_ids: event.target.checked ? [...draft.objective_ids, id] : draft.objective_ids.filter((item) => item !== id) })} /> {id}</label>)}</fieldset><label className="field">{t("assessmentPlans.activityPlannedEvidence" as never)}<textarea value={draft.planned_evidence ?? ""} onChange={(event) => setDraft({ ...draft, planned_evidence: event.target.value || null })} /></label><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.activityProcedureSteps" as never)}</legend>{draft.steps.map((step, index) => <div key={step.id} className="repeatable-row"><label className="field">{t("assessmentPlans.stepTitle" as never)}<input value={step.title} onChange={(event) => setDraft({ ...draft, steps: draft.steps.map((item, stepIndex) => stepIndex === index ? { ...item, title: event.target.value } : item) })} /></label><label className="field">{t("assessmentPlans.stepDescription" as never)}<input value={step.description} onChange={(event) => setDraft({ ...draft, steps: draft.steps.map((item, stepIndex) => stepIndex === index ? { ...item, description: event.target.value } : item) })} /></label><button type="button" className="secondary" onClick={() => setDraft({ ...draft, steps: draft.steps.filter((_, stepIndex) => stepIndex !== index) })}>{t("assessmentPlans.remove" as never)}</button></div>)}<button type="button" className="secondary" onClick={() => setDraft({ ...draft, steps: [...draft.steps, { id: generateId(), title: "", description: "" }] })}>{t("assessmentPlans.addStep" as never)}</button></fieldset><div className="workspace-actions"><button type="button" disabled={!canWrite || busy || !draft.title || !draft.description || draft.methods.length === 0} onClick={onSave}>{t("systems.saveWorkingState" as never)}</button><button type="button" className="secondary" onClick={onCancel}>{t("assessmentPlans.cancel" as never)}</button></div></div>;
}

function TaskEditor({
  draft,
  setDraft,
  canWrite,
  busy,
  activities,
  selectedSubjects,
  roles,
  onSave,
  onCancel,
  t,
}: {
  draft: AssessmentTask;
  setDraft: (draft: AssessmentTask) => void;
  canWrite: boolean;
  busy: boolean;
  activities: AssessmentActivity[];
  selectedSubjects: SubjectOption[];
  roles: AssessmentRole[];
  onSave: () => void;
  onCancel: () => void;
  t: (key: never, values?: Record<string, string | number>) => string;
}) {
  const mode = draft.on_date ? "single" : draft.start || draft.end ? "range" : "single";
  return <div className="panel stack"><label className="field">{t("assessmentPlans.taskTitle" as never)}<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="field">{t("assessmentPlans.taskDescription" as never)}<textarea value={draft.description ?? ""} onChange={(event) => setDraft({ ...draft, description: event.target.value || null })} /></label><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.taskActivities" as never)}</legend>{activities.map((activity) => <label key={activity.id}><input type="checkbox" checked={draft.activity_ids.includes(activity.id)} onChange={(event) => setDraft({ ...draft, activity_ids: event.target.checked ? [...draft.activity_ids, activity.id] : draft.activity_ids.filter((item) => item !== activity.id) })} /> {activity.title}</label>)}</fieldset><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.taskSubjects" as never)}</legend>{selectedSubjects.map((subject) => <label key={subject.uuid}><input type="checkbox" checked={draft.subject_uuids.includes(subject.uuid)} onChange={(event) => setDraft({ ...draft, subject_uuids: event.target.checked ? [...draft.subject_uuids, subject.uuid] : draft.subject_uuids.filter((item) => item !== subject.uuid) })} /> {subject.title}</label>)}</fieldset><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.taskRoles" as never)}</legend>{roles.map((role) => <label key={role.role_id}><input type="checkbox" checked={draft.role_ids.includes(role.role_id)} onChange={(event) => setDraft({ ...draft, role_ids: event.target.checked ? [...draft.role_ids, role.role_id] : draft.role_ids.filter((item) => item !== role.role_id) })} /> {role.title}</label>)}</fieldset><label className="field">{t("assessmentPlans.taskDateSingle" as never)}<input type="datetime-local" value={mode === "single" ? toLocalInput(draft.on_date) : ""} onChange={(event) => setDraft({ ...draft, on_date: toIsoInput(event.target.value), start: null, end: null })} /></label><label className="field">{t("assessmentPlans.taskDateRangeStart" as never)}<input type="datetime-local" value={mode === "range" ? toLocalInput(draft.start) : ""} onChange={(event) => setDraft({ ...draft, on_date: null, start: toIsoInput(event.target.value), end: draft.end })} /></label><label className="field">{t("assessmentPlans.taskDateRangeEnd" as never)}<input type="datetime-local" value={mode === "range" ? toLocalInput(draft.end) : ""} onChange={(event) => setDraft({ ...draft, on_date: null, start: draft.start, end: toIsoInput(event.target.value) })} /></label><div className="workspace-actions"><button type="button" disabled={!canWrite || busy || !draft.title} onClick={onSave}>{t("systems.saveWorkingState" as never)}</button><button type="button" className="secondary" onClick={onCancel}>{t("assessmentPlans.cancel" as never)}</button></div></div>;
}

function RoleEditor({
  draft,
  setDraft,
  parties,
  onSave,
  onCancel,
  t,
}: {
  draft: AssessmentRole;
  setDraft: (draft: AssessmentRole) => void;
  parties: AssessmentParty[];
  onSave: () => void;
  onCancel: () => void;
  t: (key: never, values?: Record<string, string | number>) => string;
}) {
  return <div className="panel stack"><label className="field">{t("assessmentPlans.roleId" as never)}<input value={draft.role_id} onChange={(event) => setDraft({ ...draft, role_id: event.target.value })} /></label><label className="field">{t("assessmentPlans.roleTitle" as never)}<input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label className="field">{t("assessmentPlans.roleDescription" as never)}<textarea value={draft.description ?? ""} onChange={(event) => setDraft({ ...draft, description: event.target.value || null })} /></label><fieldset className="repeatable-fields"><legend>{t("assessmentPlans.roleParties" as never)}</legend>{parties.map((party) => <label key={party.uuid}><input type="checkbox" checked={draft.party_uuids.includes(party.uuid)} onChange={(event) => setDraft({ ...draft, party_uuids: event.target.checked ? [...draft.party_uuids, party.uuid] : draft.party_uuids.filter((item) => item !== party.uuid) })} /> {party.name}</label>)}</fieldset><div className="workspace-actions"><button type="button" onClick={onSave}>{t("systems.saveWorkingState" as never)}</button><button type="button" className="secondary" onClick={onCancel}>{t("assessmentPlans.cancel" as never)}</button></div></div>;
}

function PartyEditor({
  draft,
  setDraft,
  onSave,
  onCancel,
  t,
}: {
  draft: AssessmentParty;
  setDraft: (draft: AssessmentParty) => void;
  onSave: () => void;
  onCancel: () => void;
  t: (key: never, values?: Record<string, string | number>) => string;
}) {
  return <div className="panel stack"><label className="field">{t("assessmentPlans.partyType" as never)}<select value={draft.party_type} onChange={(event) => setDraft({ ...draft, party_type: event.target.value as AssessmentParty["party_type"] })}><option value="person">{t("assessmentPlans.partyPerson" as never)}</option><option value="organization">{t("assessmentPlans.partyOrganization" as never)}</option></select></label><label className="field">{t("assessmentPlans.partyName" as never)}<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label><div className="workspace-actions"><button type="button" onClick={onSave}>{t("systems.saveWorkingState" as never)}</button><button type="button" className="secondary" onClick={onCancel}>{t("assessmentPlans.cancel" as never)}</button></div></div>;
}

function nextLocalObjectiveId(items: AssessmentLocalObjective[], controlId: string): string {
  const prefix = `local-${controlId.toLowerCase()}`;
  let counter = 1;
  while (items.some((item) => item.objective_id === `${prefix}-${counter}`)) counter += 1;
  return `${prefix}-${counter}`;
}

function planSnapshot(plan: AssessmentPlan) {
  return {
    title: plan.title,
    description: plan.description,
    control_ids: plan.control_ids,
    source_objectives: plan.source_objectives,
    local_objectives: plan.local_objectives,
    subject_uuids: plan.subject_uuids,
    activities: plan.activities,
    tasks: plan.tasks,
    roles: plan.roles,
    parties: plan.parties,
    terms: plan.terms,
  };
}

function methodLabel(method: AssessmentMethod, t?: (key: never, values?: Record<string, string | number>) => string) {
  if (!t) return method;
  if (method === "EXAMINE") return t("assessmentPlans.method.examine" as never);
  if (method === "INTERVIEW") return t("assessmentPlans.method.interview" as never);
  return t("assessmentPlans.method.test" as never);
}

function diagnosticGuidance(code: string, t: (key: never, values?: Record<string, string | number>) => string) {
  if (code.includes("control") || code.includes("objective")) {
    return t("assessmentPlans.validationScope" as never, {
      section: t("assessmentPlans.scope" as never),
    });
  }
  if (code.includes("activity")) {
    return t("assessmentPlans.validationScope" as never, {
      section: t("assessmentPlans.activities" as never),
    });
  }
  if (code.includes("task") || code.includes("role") || code.includes("party")) {
    return t("assessmentPlans.validationScope" as never, {
      section: t("assessmentPlans.tasks" as never),
    });
  }
  return t("assessmentPlans.validationAction" as never, {
    action: t("assessmentPlans.validationSaveFirst" as never),
  });
}

function toLocalInput(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hour = String(date.getUTCHours()).padStart(2, "0");
  const minute = String(date.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function toIsoInput(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(`${value}:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function generateId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}



