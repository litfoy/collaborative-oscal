"use client";

import { useMemo, useState, type FormEvent } from "react";

import { bffWrite } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
import type {
  AssessmentPlan,
  AssessmentPlanVersion,
  AssessmentResult,
  InformationSystem,
} from "@/lib/types";

export interface AssessmentResultOverviewItem {
  result: AssessmentResult;
  system: InformationSystem;
  plan: AssessmentPlan | null;
  planVersion: AssessmentPlanVersion | null;
  immutableVersionCount: number;
}

export function AssessmentResultsWorkspace({
  tenantId,
  items,
  systems,
  plansBySystem,
  versionsByPlan,
  canWrite,
}: {
  tenantId: string;
  items: AssessmentResultOverviewItem[];
  systems: InformationSystem[];
  plansBySystem: Record<string, AssessmentPlan[]>;
  versionsByPlan: Record<string, AssessmentPlanVersion[]>;
  canWrite: boolean;
}) {
  const { t, number, errorMessage } = useI18n();
  const [results, setResults] = useState(items);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [systemId, setSystemId] = useState("");
  const [planId, setPlanId] = useState("");
  const [planVersionId, setPlanVersionId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return results;
    return results.filter((item) =>
      [
        item.result.title,
        item.system.name,
        item.plan?.title ?? "",
        item.planVersion?.document_version ?? "",
      ]
        .join("\n")
        .toLowerCase()
        .includes(term),
    );
  }, [query, results]);

  const plans = systemId ? plansBySystem[systemId] ?? [] : [];
  const versions = planId ? versionsByPlan[planId] ?? [] : [];

  async function createResult(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!systemId || !planId || !planVersionId || !title.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await bffWrite<AssessmentResult>(
        "POST",
        `tenants/${tenantId}/systems/${systemId}/assessment-results`,
        {
          assessment_plan_id: planId,
          assessment_plan_version_id: planVersionId,
          title: title.trim(),
          description: description.trim() || null,
        },
      );
      const system = systems.find((item) => item.id === systemId) ?? null;
      const plan = plans.find((item) => item.id === planId) ?? null;
      const planVersion = versions.find((item) => item.id === planVersionId) ?? null;
      if (system) {
        setResults((current) => [
          {
            result: created,
            system,
            plan,
            planVersion,
            immutableVersionCount: 0,
          },
          ...current,
        ]);
      }
      setNotice(t("assessmentResults.created"));
      setCreating(false);
      setSystemId("");
      setPlanId("");
      setPlanVersionId("");
      setTitle("");
      setDescription("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace system-workspace">
      <h1>{t("assessmentResults.sectionTitle")}</h1>
      <p className="muted">{t("assessmentResults.workspaceIntro")}</p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}

      <div className="workspace-actions">
        <label className="field">
          {t("assessmentResults.searchResults")}
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        {canWrite ? (
          <button type="button" onClick={() => setCreating((value) => !value)}>
            {creating ? t("assessmentResults.cancel") : t("assessmentResults.newResult")}
          </button>
        ) : null}
      </div>

      {creating ? (
        <form className="panel stack" onSubmit={createResult}>
          <h2>{t("assessmentResults.createWorkflow")}</h2>
          <label className="field">
            {t("assessmentResults.selectSystem")}
            <select
              required
              value={systemId}
              onChange={(event) => {
                setSystemId(event.target.value);
                setPlanId("");
                setPlanVersionId("");
              }}
            >
              <option value="">{t("assessmentResults.selectSystemPlaceholder")}</option>
              {systems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("assessmentResults.selectPlan")}
            <select
              required
              value={planId}
              disabled={!systemId}
              onChange={(event) => {
                setPlanId(event.target.value);
                setPlanVersionId("");
              }}
            >
              <option value="">{t("assessmentResults.selectPlanPlaceholder")}</option>
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.title}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("assessmentResults.planVersion")}
            <select
              required
              value={planVersionId}
              disabled={!planId}
              onChange={(event) => setPlanVersionId(event.target.value)}
            >
              <option value="">{t("assessmentResults.selectPlanVersion")}</option>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  {version.document_version} · OSCAL {version.oscal_version}
                </option>
              ))}
            </select>
          </label>
          {planId && versions.length === 0 ? (
            <p className="muted">{t("assessmentResults.noPlanVersions")}</p>
          ) : null}
          <p className="muted">{t("assessmentResults.immutableSelectionHint")}</p>
          <label className="field">
            {t("assessmentResults.title")}
            <input required value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field">
            {t("assessmentResults.description")}
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="workspace-actions">
            <button disabled={busy || !systemId || !planId || !planVersionId || !title.trim()}>
              {t("assessmentResults.createAction")}
            </button>
            <button type="button" className="secondary" onClick={() => setCreating(false)}>
              {t("assessmentResults.cancel")}
            </button>
          </div>
        </form>
      ) : null}

      {filtered.length ? (
        <ul className="profile-list">
          {filtered.map((item) => (
            <li key={item.result.id}>
              <h3>{item.result.title}</h3>
              <p>
                {item.system.name} · {item.plan?.title ?? t("common.notRecorded")}
              </p>
              <p className="muted">
                {t("assessmentResults.planVersion")}: {item.planVersion?.document_version ?? t("common.notRecorded")}
              </p>
              <p className="muted">
                {t("assessmentResults.scopeSummary", {
                  controls: number(item.result.reviewed_control_ids.length),
                  observations: number(item.result.observations.length),
                  findings: number(item.result.findings.length),
                })}
              </p>
              <p className="muted">
                {t("assessmentPlans.versionCount")}: {number(item.immutableVersionCount)}
              </p>
              <a
                className="button"
                href={`/t/${tenantId}/systems/${item.system.id}/assessment-results/${item.result.id}`}
              >
                {t("assessmentResults.openResult")}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t("assessmentResults.noResultsWorkspace")}</p>
      )}
    </div>
  );
}

