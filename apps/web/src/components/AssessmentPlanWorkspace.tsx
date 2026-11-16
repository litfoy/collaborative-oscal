"use client";

import { useState, type FormEvent } from "react";

import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
import type {
  AssessmentPlan,
  AssessmentPlanValidation,
  AssessmentPlanVersion,
  InformationSystem,
} from "@/lib/types";

export function AssessmentPlanWorkspace({
  tenantId,
  system,
  initialPlan,
  initialValidation,
  initialVersions,
  canWrite,
}: {
  tenantId: string;
  system: InformationSystem;
  initialPlan: AssessmentPlan;
  initialValidation: AssessmentPlanValidation;
  initialVersions: AssessmentPlanVersion[];
  canWrite: boolean;
}) {
  const { t, date, errorMessage } = useI18n();
  const [plan, setPlan] = useState(initialPlan);
  const [savedPlan, setSavedPlan] = useState(initialPlan);
  const [validation, setValidation] = useState(initialValidation);
  const [versions, setVersions] = useState(initialVersions);
  const [tab, setTab] = useState<"overview" | "scope" | "activities" | "tasks" | "validation">("overview");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [sourceObjectives, setSourceObjectives] = useState(
    JSON.stringify(plan.source_objectives, null, 2),
  );
  const [localObjectives, setLocalObjectives] = useState(
    JSON.stringify(plan.local_objectives, null, 2),
  );
  const [activities, setActivities] = useState(JSON.stringify(plan.activities, null, 2));
  const [tasks, setTasks] = useState(JSON.stringify(plan.tasks, null, 2));
  const [roles, setRoles] = useState(JSON.stringify(plan.roles, null, 2));
  const [parties, setParties] = useState(JSON.stringify(plan.parties, null, 2));

  const controlsText = plan.control_ids.join("\n");
  const subjectsText = plan.subject_uuids.join("\n");
  const [controls, setControls] = useState(controlsText);
  const [subjects, setSubjects] = useState(subjectsText);

  const dirty =
    plan.title !== savedPlan.title ||
    (plan.description ?? "") !== (savedPlan.description ?? "") ||
    controls !== savedPlan.control_ids.join("\n") ||
    subjects !== savedPlan.subject_uuids.join("\n") ||
    sourceObjectives !== JSON.stringify(savedPlan.source_objectives, null, 2) ||
    localObjectives !== JSON.stringify(savedPlan.local_objectives, null, 2) ||
    activities !== JSON.stringify(savedPlan.activities, null, 2) ||
    tasks !== JSON.stringify(savedPlan.tasks, null, 2) ||
    roles !== JSON.stringify(savedPlan.roles, null, 2) ||
    parties !== JSON.stringify(savedPlan.parties, null, 2);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const payload = buildPayload();
      const updated = await request<AssessmentPlan>(
        `/bff/tenants/${tenantId}/assessment-plans/${plan.id}`,
        "PUT",
        payload,
        t,
        errorMessage,
      );
      setPlan(updated);
      setSavedPlan(updated);
      setSourceObjectives(JSON.stringify(updated.source_objectives, null, 2));
      setLocalObjectives(JSON.stringify(updated.local_objectives, null, 2));
      setActivities(JSON.stringify(updated.activities, null, 2));
      setTasks(JSON.stringify(updated.tasks, null, 2));
      setRoles(JSON.stringify(updated.roles, null, 2));
      setParties(JSON.stringify(updated.parties, null, 2));
      setControls(updated.control_ids.join("\n"));
      setSubjects(updated.subject_uuids.join("\n"));
      return t("assessmentPlans.saved");
    });
  }

  async function validatePlan() {
    await run(async () => {
      const result = await getJson<AssessmentPlanValidation>(
        `/bff/tenants/${tenantId}/assessment-plans/${plan.id}/validation`,
        t,
        errorMessage,
      );
      setValidation(result);
      return result.valid
        ? t("assessmentPlans.validationPassed")
        : t("assessmentPlans.validationIssues");
    });
  }

  async function createVersion() {
    await run(async () => {
      const version = await request<AssessmentPlanVersion>(
        `/bff/tenants/${tenantId}/assessment-plans/${plan.id}/versions`,
        "POST",
        {},
        t,
        errorMessage,
      );
      setVersions((current) => [version, ...current.filter((item) => item.id !== version.id)]);
      return version.created
        ? t("assessmentPlans.versionCreated", { version: version.document_version })
        : t("assessmentPlans.versionUnchanged");
    });
  }

  function buildPayload() {
    return {
      title: plan.title,
      description: plan.description,
      control_ids: splitLines(controls),
      source_objectives: parseJson(sourceObjectives, "source objectives"),
      local_objectives: parseJson(localObjectives, "local objectives"),
      subject_uuids: splitLines(subjects),
      activities: parseJson(activities, "activities"),
      tasks: parseJson(tasks, "tasks"),
      roles: parseJson(roles, "roles"),
      parties: parseJson(parties, "parties"),
      terms: plan.terms,
    };
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

  return (
    <div className="workspace system-workspace">
      <a href={`/t/${tenantId}/systems/${system.id}`}>{t("assessmentPlans.backToSystem")}</a>
      <h1>{plan.title}</h1>
      <p className="muted">
        {t("assessmentPlans.pinnedSspVersion", {
          version: plan.system_security_plan_version_id,
        })}
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {dirty ? <p role="status">{t("systems.unsavedWorkingChanges")}</p> : null}

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
            <input
              value={plan.title}
              onChange={(event) => setPlan({ ...plan, title: event.target.value })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            {t("assessmentPlans.description")}
            <textarea
              value={plan.description ?? ""}
              onChange={(event) => setPlan({ ...plan, description: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            {t("assessmentPlans.terms")}
            <textarea
              value={plan.terms ?? ""}
              onChange={(event) => setPlan({ ...plan, terms: event.target.value || null })}
              disabled={!canWrite || busy}
            />
          </label>
        </section>

        <section className="panel" hidden={tab !== "scope"}>
          <label className="field">
            Controls (one control-id per line)
            <textarea value={controls} onChange={(event) => setControls(event.target.value)} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            Subject UUIDs (one UUID per line)
            <textarea value={subjects} onChange={(event) => setSubjects(event.target.value)} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            {t("assessmentPlans.sourceObjectives")} (JSON)
            <textarea value={sourceObjectives} onChange={(event) => setSourceObjectives(event.target.value)} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            {t("assessmentPlans.localObjectives")} (JSON)
            <textarea value={localObjectives} onChange={(event) => setLocalObjectives(event.target.value)} disabled={!canWrite || busy} />
          </label>
        </section>

        <section className="panel" hidden={tab !== "activities"}>
          <label className="field">
            {t("assessmentPlans.activities")} (JSON)
            <textarea value={activities} onChange={(event) => setActivities(event.target.value)} disabled={!canWrite || busy} />
          </label>
        </section>

        <section className="panel" hidden={tab !== "tasks"}>
          <label className="field">
            {t("assessmentPlans.tasks")} (JSON)
            <textarea value={tasks} onChange={(event) => setTasks(event.target.value)} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            Roles (JSON)
            <textarea value={roles} onChange={(event) => setRoles(event.target.value)} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            Parties (JSON)
            <textarea value={parties} onChange={(event) => setParties(event.target.value)} disabled={!canWrite || busy} />
          </label>
        </section>

        <section className="panel" hidden={tab !== "validation"}>
          <div className="workspace-actions">
            <button type="button" onClick={() => void validatePlan()} disabled={busy}>
              {t("assessmentPlans.validate")}
            </button>
            {canWrite ? (
              <button type="button" onClick={() => void createVersion()} disabled={busy || dirty}>
                {t("assessmentPlans.createVersion")}
              </button>
            ) : null}
          </div>
          <p className="muted">
            {validation.valid ? t("assessmentPlans.validationPassed") : t("assessmentPlans.validationIssues")}
          </p>
          {validation.diagnostics.length ? (
            <ul>
              {validation.diagnostics.map((item, index) => (
                <li key={`${item.code}:${index}`}>{item.message}</li>
              ))}
            </ul>
          ) : null}
          <h3>{t("systems.versions")}</h3>
          {versions.length ? (
            <ul className="profile-list">
              {versions.map((version) => (
                <li key={version.id}>
                  <strong>{version.document_version}</strong>
                  <p className="muted">{date(version.created_at)}</p>
                  <a href={`/bff/tenants/${tenantId}/assessment-plans/${plan.id}/versions/${version.id}/export`}>
                    {t("systems.exportStoredOscalJson")}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("systems.noImmutableVersions")}</p>
          )}
        </section>

        {canWrite ? <button disabled={busy}>{t("assessmentPlans.save")}</button> : null}
      </form>
    </div>
  );
}

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseJson(value: string, fieldName: string): unknown[] {
  const parsed = JSON.parse(value || "[]") as unknown;
  if (!Array.isArray(parsed)) {
    throw new Error(`${fieldName} must be a JSON array.`);
  }
  return parsed;
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

async function getJson<T>(
  path: string,
  t: Translate,
  errorMessage: (error: unknown) => string,
): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  const result: unknown = await response.json();
  if (!response.ok) throw new Error(readError(result, t, errorMessage));
  return result as T;
}

function readError(
  body: unknown,
  t: Translate,
  errorMessage: (error: unknown) => string,
): string {
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

