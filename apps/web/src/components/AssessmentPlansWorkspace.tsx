"use client";

import { useMemo, useState, type FormEvent } from "react";

import { bffWrite } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
import type {
  AssessmentPlan,
  InformationSystem,
  RevisionSummary,
  SystemSecurityPlan,
  SystemSecurityPlanVersion,
} from "@/lib/types";

export interface AssessmentPlanOverviewItem {
  plan: AssessmentPlan;
  system: InformationSystem;
  ssp: SystemSecurityPlan | null;
  sspVersion: SystemSecurityPlanVersion | null;
  revision: RevisionSummary | null;
  immutableVersionCount: number;
}

export function AssessmentPlansWorkspace({
  tenantId,
  items,
  systems,
  sspBySystem,
  versionsBySsp,
  revisionsBySsp,
  canWrite,
}: {
  tenantId: string;
  items: AssessmentPlanOverviewItem[];
  systems: InformationSystem[];
  sspBySystem: Record<string, SystemSecurityPlan[]>;
  versionsBySsp: Record<string, SystemSecurityPlanVersion[]>;
  revisionsBySsp: Record<string, RevisionSummary | null>;
  canWrite: boolean;
}) {
  const { t, number, date, errorMessage } = useI18n();
  const [plans, setPlans] = useState(items);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [systemId, setSystemId] = useState("");
  const [sspId, setSspId] = useState("");
  const [sspVersionId, setSspVersionId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return plans;
    return plans.filter((item) => {
      const revisionPart = item.revision ? String(item.revision.revision_number) : "";
      return [
        item.plan.title,
        item.system.name,
        item.ssp?.title ?? "",
        item.ssp?.catalog_name ?? "",
        revisionPart,
      ]
        .join("\n")
        .toLowerCase()
        .includes(term);
    });
  }, [plans, query]);

  const ssps = systemId ? sspBySystem[systemId] ?? [] : [];
  const versions = sspId ? versionsBySsp[sspId] ?? [] : [];

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!systemId || !sspVersionId || !title.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await bffWrite<AssessmentPlan>(
        "POST",
        `tenants/${tenantId}/systems/${systemId}/assessment-plans`,
        {
          ssp_version_id: sspVersionId,
          title: title.trim(),
          description: description.trim() || null,
        },
      );
      const system = systems.find((item) => item.id === systemId) ?? null;
      const ssp = ssps.find((item) => item.id === sspId) ?? null;
      const sspVersion = versions.find((item) => item.id === sspVersionId) ?? null;
      const revision = ssp ? revisionsBySsp[ssp.id] ?? null : null;
      if (system) {
        setPlans((current) => [
          {
            plan: created,
            system,
            ssp,
            sspVersion,
            revision,
            immutableVersionCount: 0,
          },
          ...current,
        ]);
      }
      setNotice(t("assessmentPlans.created"));
      setCreating(false);
      setSystemId("");
      setSspId("");
      setSspVersionId("");
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
      <h1>{t("assessmentPlans.sectionTitle")}</h1>
      <p className="muted">{t("assessmentPlans.workspaceIntro")}</p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}

      <div className="workspace-actions">
        <label className="field">
          {t("assessmentPlans.searchPlans")}
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        {canWrite ? (
          <button type="button" onClick={() => setCreating((current) => !current)}>
            {creating ? t("assessmentPlans.cancel") : t("assessmentPlans.newPlan")}
          </button>
        ) : null}
      </div>

      {creating ? (
        <form className="panel stack" onSubmit={createPlan}>
          <h2>{t("assessmentPlans.createWorkflow")}</h2>
          <label className="field">
            {t("assessmentPlans.selectSystem")}
            <select
              required
              value={systemId}
              onChange={(event) => {
                setSystemId(event.target.value);
                setSspId("");
                setSspVersionId("");
              }}
            >
              <option value="">{t("assessmentPlans.selectSystemPlaceholder")}</option>
              {systems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("assessmentPlans.selectSsp")}
            <select
              required
              value={sspId}
              disabled={!systemId}
              onChange={(event) => {
                setSspId(event.target.value);
                setSspVersionId("");
              }}
            >
              <option value="">{t("assessmentPlans.selectSspPlaceholder")}</option>
              {ssps.map((ssp) => (
                <option key={ssp.id} value={ssp.id}>
                  {ssp.title} · {ssp.catalog_name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("assessmentPlans.sspVersion")}
            <select
              required
              value={sspVersionId}
              disabled={!sspId}
              onChange={(event) => setSspVersionId(event.target.value)}
            >
              <option value="">{t("assessmentPlans.selectSspVersion")}</option>
              {versions.map((version) => (
                <option key={version.id} value={version.id}>
                  {version.document_version} · OSCAL {version.oscal_version} · {date(version.created_at)}
                </option>
              ))}
            </select>
          </label>
          {sspId && versions.length === 0 ? <p className="muted">{t("assessmentPlans.noSspVersions")}</p> : null}
          <p className="muted">{t("assessmentPlans.immutableSelectionHint")}</p>
          <label className="field">
            {t("assessmentPlans.title")}
            <input required value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label className="field">
            {t("assessmentPlans.description")}
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="workspace-actions">
            <button disabled={busy || !systemId || !sspVersionId || !title.trim()}>
              {t("assessmentPlans.createAction")}
            </button>
            <button type="button" className="secondary" onClick={() => setCreating(false)}>
              {t("assessmentPlans.cancel")}
            </button>
          </div>
        </form>
      ) : null}

      {filtered.length ? (
        <ul className="profile-list">
          {filtered.map((item) => (
            <li key={item.plan.id}>
              <h3>{item.plan.title}</h3>
              <p>
                {item.system.name} · {item.ssp?.title ?? t("common.notRecorded")}
              </p>
              <p className="muted">
                {t("assessmentPlans.pinnedVersion")}: {item.sspVersion?.document_version ?? t("common.notRecorded")}
                {item.revision ? ` · ${t("common.revisionNumber", { number: number(item.revision.revision_number) })}` : ""}
              </p>
              <p className="muted">
                {t("assessmentPlans.baseline")}: {item.ssp?.catalog_name ?? t("common.notRecorded")}
              </p>
              <p className="muted">
                {t("assessmentPlans.requirementsCount")}: {number(item.plan.control_ids.length)} · {t("assessmentPlans.activitiesCount")}: {number(item.plan.activities.length)} · {t("assessmentPlans.tasksCount")}: {number(item.plan.tasks.length)} · {t("assessmentPlans.versionCount")}: {number(item.immutableVersionCount)}
              </p>
              <a className="button" href={`/t/${tenantId}/systems/${item.system.id}/assessment-plans/${item.plan.id}`}>
                {t("assessmentPlans.openPlan")}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t("assessmentPlans.noPlansWorkspace")}</p>
      )}
    </div>
  );
}

