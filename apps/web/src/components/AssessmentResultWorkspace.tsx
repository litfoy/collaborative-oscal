"use client";

import { useMemo, useState, type FormEvent } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import { useI18n } from "@/lib/i18n/provider";
import type {
  AssessmentMethod,
  AssessmentPlan,
  AssessmentResult,
  AssessmentResultEvidence,
  AssessmentResultFinding,
  AssessmentResultObservation,
  AssessmentResultValidation,
  AssessmentResultVersion,
  InformationSystem,
} from "@/lib/types";

const METHODS: AssessmentMethod[] = ["EXAMINE", "INTERVIEW", "TEST"];

type Tab = "overview" | "observations" | "findings" | "validation";

export function AssessmentResultWorkspace({
  tenantId,
  system,
  plan,
  initialResult,
  initialValidation,
  initialVersions,
  canWrite,
}: {
  tenantId: string;
  system: InformationSystem;
  plan: AssessmentPlan;
  initialResult: AssessmentResult;
  initialValidation: AssessmentResultValidation;
  initialVersions: AssessmentResultVersion[];
  canWrite: boolean;
}) {
  const { t, date, number, enumLabel, errorMessage } = useI18n();
  const [result, setResult] = useState(initialResult);
  const [savedResult, setSavedResult] = useState(initialResult);
  const [validation, setValidation] = useState(initialValidation);
  const [validationStale, setValidationStale] = useState(false);
  const [versions, setVersions] = useState(initialVersions);
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const dirty = useMemo(
    () => JSON.stringify(snapshot(result)) !== JSON.stringify(snapshot(savedResult)),
    [result, savedResult],
  );

  const statementTargetOptions = useMemo(
    () =>
      result.statement_options.filter((item) =>
        result.reviewed_control_ids.includes(item.control_id),
      ),
    [result.reviewed_control_ids, result.statement_options],
  );

  const objectiveTargetOptions = useMemo(
    () =>
      result.objective_options.filter((item) =>
        result.reviewed_control_ids.includes(item.control_id),
      ),
    [result.objective_options, result.reviewed_control_ids],
  );

  function updateResult(next: AssessmentResult) {
    setResult(next);
    setValidationStale(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const updated = await bffWrite<AssessmentResult>(
        "PUT",
        `tenants/${tenantId}/assessment-results/${result.id}`,
        {
          title: result.title,
          description: result.description,
          reviewed_control_ids: result.reviewed_control_ids,
          observations: result.observations,
          findings: result.findings,
          start: result.start,
          end: result.end,
        },
      );
      setResult(updated);
      setSavedResult(updated);
      setValidationStale(true);
      return t("assessmentResults.saved");
    });
  }

  async function validateResult() {
    if (dirty) {
      setNotice(t("assessmentResults.validationSaveFirst"));
      return;
    }
    await run(async () => {
      const value = await bffGet<AssessmentResultValidation>(
        `tenants/${tenantId}/assessment-results/${result.id}/validation`,
      );
      setValidation(value);
      setValidationStale(false);
      return value.valid
        ? t("assessmentResults.validationPassed")
        : t("assessmentResults.validationIssues");
    });
  }

  async function createVersion() {
    await run(async () => {
      const version = await bffWrite<AssessmentResultVersion>(
        "POST",
        `tenants/${tenantId}/assessment-results/${result.id}/versions`,
        {},
      );
      setVersions((current) => [version, ...current.filter((item) => item.id !== version.id)]);
      return version.created
        ? t("assessmentResults.versionCreated", { version: version.document_version })
        : t("assessmentResults.versionUnchanged");
    });
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setNotice(await action());
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  function addObservation() {
    updateResult({
      ...result,
      observations: [
        ...result.observations,
        {
          id: generateId(),
          title: "",
          description: "",
          methods: [],
          collected_at: new Date().toISOString(),
          subject_uuids: [],
          evidence: [],
        },
      ],
    });
  }

  function updateObservation(index: number, next: AssessmentResultObservation) {
    updateResult({
      ...result,
      observations: result.observations.map((item, itemIndex) =>
        itemIndex === index ? next : item,
      ),
    });
  }

  function removeObservation(index: number) {
    const removedId = result.observations[index]?.id;
    const referencedBy = result.findings
      .filter((finding) => finding.related_observation_ids.includes(String(removedId)))
      .map((finding) => finding.title || finding.id);
    if (referencedBy.length) {
      setError(
        t("assessmentResults.cannotRemoveObservationInUse", {
          findings: referencedBy.join(", "),
        }),
      );
      return;
    }
    updateResult({
      ...result,
      observations: result.observations.filter((_, itemIndex) => itemIndex !== index),
    });
  }

  function addFinding() {
    const defaultTarget =
      statementTargetOptions[0]?.statement_id ?? objectiveTargetOptions[0]?.objective_id ?? "";
    const defaultType = statementTargetOptions.length ? "statement-id" : "objective-id";
    updateResult({
      ...result,
      findings: [
        ...result.findings,
        {
          id: generateId(),
          title: "",
          description: "",
          target_type: defaultType,
          target_id: defaultTarget,
          status: "other",
          related_observation_ids: [],
        },
      ],
    });
  }

  function updateFinding(index: number, next: AssessmentResultFinding) {
    updateResult({
      ...result,
      findings: result.findings.map((item, itemIndex) => (itemIndex === index ? next : item)),
    });
  }

  function removeFinding(index: number) {
    updateResult({
      ...result,
      findings: result.findings.filter((_, itemIndex) => itemIndex !== index),
    });
  }

  return (
    <div className="workspace system-workspace">
      <a href={`/t/${tenantId}/systems/${system.id}`}>{t("assessmentResults.backToSystem")}</a>
      <h1>{result.title}</h1>
      <p className="muted">
        {system.name} · {plan.title}
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {dirty ? <p role="status">{t("systems.unsavedWorkingChanges")}</p> : null}
      {validationStale ? <p role="status">{t("assessmentResults.validationOutdated")}</p> : null}

      <nav className="workspace-tabs" aria-label={t("assessmentResults.sectionTitle") as string}>
        {([
          ["overview", t("assessmentResults.overview")],
          ["observations", t("assessmentResults.observations")],
          ["findings", t("assessmentResults.findings")],
          ["validation", t("assessmentResults.validationVersions")],
        ] as const).map(([id, label]) => (
          <button key={id} type="button" aria-current={tab === id ? "page" : undefined} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>

      <form className="stack" onSubmit={save}>
        <section className="panel" hidden={tab !== "overview"}>
          <label className="field">
            {t("assessmentResults.title")}
            <input value={result.title} onChange={(event) => updateResult({ ...result, title: event.target.value })} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            {t("assessmentResults.description")}
            <textarea value={result.description ?? ""} onChange={(event) => updateResult({ ...result, description: event.target.value || null })} disabled={!canWrite || busy} />
          </label>
          <label className="field">
            {t("assessmentResults.reviewedControls")}
            <select
              multiple
              value={result.reviewed_control_ids}
              onChange={(event) =>
                updateResult({
                  ...result,
                  reviewed_control_ids: Array.from(event.target.selectedOptions).map((item) => item.value),
                })
              }
              disabled={!canWrite || busy}
            >
              {result.planned_control_ids.map((controlId) => (
                <option key={controlId} value={controlId}>
                  {controlId}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("assessmentResults.start")}
            <input
              type="datetime-local"
              value={toLocalInput(result.start)}
              onChange={(event) => updateResult({ ...result, start: toIsoInput(event.target.value) })}
              disabled={!canWrite || busy}
            />
          </label>
          <label className="field">
            {t("assessmentResults.end")}
            <input
              type="datetime-local"
              value={toLocalInput(result.end)}
              onChange={(event) => updateResult({ ...result, end: toIsoInput(event.target.value) })}
              disabled={!canWrite || busy}
            />
          </label>
          <p className="muted">
            {t("assessmentResults.scopeSummary", {
              controls: number(result.reviewed_control_ids.length),
              observations: number(result.observations.length),
              findings: number(result.findings.length),
            })}
          </p>
        </section>

        <section className="panel" hidden={tab !== "observations"}>
          <div className="workspace-actions">
            <button type="button" disabled={!canWrite || busy} onClick={addObservation}>
              {t("assessmentResults.addObservation")}
            </button>
          </div>
          {result.observations.length ? (
            <ul className="profile-list">
              {result.observations.map((observation, index) => (
                <li key={observation.id}>
                  <label className="field">
                    {t("assessmentResults.observationTitle")}
                    <input value={observation.title} onChange={(event) => updateObservation(index, { ...observation, title: event.target.value })} disabled={!canWrite || busy} />
                  </label>
                  <label className="field">
                    {t("assessmentResults.observationDescription")}
                    <textarea value={observation.description} onChange={(event) => updateObservation(index, { ...observation, description: event.target.value })} disabled={!canWrite || busy} />
                  </label>
                  <label className="field">
                    {t("assessmentResults.collectedAt")}
                    <input type="datetime-local" value={toLocalInput(observation.collected_at)} onChange={(event) => updateObservation(index, { ...observation, collected_at: toIsoInput(event.target.value) ?? observation.collected_at })} disabled={!canWrite || busy} />
                  </label>
                  <fieldset className="repeatable-fields">
                    <legend>{t("assessmentResults.methods")}</legend>
                    {METHODS.map((method) => (
                      <label key={method}>
                        <input
                          type="checkbox"
                          checked={observation.methods.includes(method)}
                          onChange={(event) =>
                            updateObservation(index, {
                              ...observation,
                              methods: event.target.checked
                                ? [...observation.methods, method]
                                : observation.methods.filter((item) => item !== method),
                            })
                          }
                          disabled={!canWrite || busy}
                        />
                        {enumLabel(method)}
                      </label>
                    ))}
                  </fieldset>
                  <fieldset className="repeatable-fields">
                    <legend>{t("assessmentResults.subjects")}</legend>
                    {result.subject_options.map((subject) => (
                      <label key={subject.uuid}>
                        <input
                          type="checkbox"
                          checked={observation.subject_uuids.includes(subject.uuid)}
                          onChange={(event) =>
                            updateObservation(index, {
                              ...observation,
                              subject_uuids: event.target.checked
                                ? [...observation.subject_uuids, subject.uuid]
                                : observation.subject_uuids.filter((item) => item !== subject.uuid),
                            })
                          }
                          disabled={!canWrite || busy}
                        />
                        {subject.title} · {enumLabel(subject.type)}
                      </label>
                    ))}
                  </fieldset>
                  <h4>{t("assessmentResults.evidence")}</h4>
                  {observation.evidence.map((entry, evidenceIndex) => (
                    <div key={entry.id} className="panel stack">
                      <label className="field">
                        {t("assessmentResults.evidenceTitle")}
                        <input
                          value={entry.title}
                          onChange={(event) =>
                            updateObservation(index, {
                              ...observation,
                              evidence: observation.evidence.map((item, itemIndex) =>
                                itemIndex === evidenceIndex
                                  ? { ...item, title: event.target.value }
                                  : item,
                              ),
                            })
                          }
                          disabled={!canWrite || busy}
                        />
                      </label>
                      <label className="field">
                        {t("assessmentResults.evidenceDescription")}
                        <textarea
                          value={entry.description}
                          onChange={(event) =>
                            updateObservation(index, {
                              ...observation,
                              evidence: observation.evidence.map((item, itemIndex) =>
                                itemIndex === evidenceIndex
                                  ? { ...item, description: event.target.value }
                                  : item,
                              ),
                            })
                          }
                          disabled={!canWrite || busy}
                        />
                      </label>
                      <label className="field">
                        {t("assessmentResults.evidenceHref")}
                        <input
                          value={entry.href ?? ""}
                          onChange={(event) =>
                            updateObservation(index, {
                              ...observation,
                              evidence: observation.evidence.map((item, itemIndex) =>
                                itemIndex === evidenceIndex
                                  ? { ...item, href: event.target.value || null }
                                  : item,
                              ),
                            })
                          }
                          disabled={!canWrite || busy}
                        />
                      </label>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() =>
                          updateObservation(index, {
                            ...observation,
                            evidence: observation.evidence.filter((_, itemIndex) => itemIndex !== evidenceIndex),
                          })
                        }
                        disabled={!canWrite || busy}
                      >
                        {t("assessmentResults.remove")}
                      </button>
                    </div>
                  ))}
                  <div className="workspace-actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        updateObservation(index, {
                          ...observation,
                          evidence: [
                            ...observation.evidence,
                            {
                              id: generateId(),
                              title: "",
                              description: "",
                              href: null,
                            } as AssessmentResultEvidence,
                          ],
                        })
                      }
                      disabled={!canWrite || busy}
                    >
                      {t("assessmentResults.addEvidence")}
                    </button>
                    <button type="button" className="secondary" onClick={() => removeObservation(index)} disabled={!canWrite || busy}>
                      {t("assessmentResults.remove")}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("assessmentResults.noObservations")}</p>
          )}
        </section>

        <section className="panel" hidden={tab !== "findings"}>
          <div className="workspace-actions">
            <button type="button" disabled={!canWrite || busy} onClick={addFinding}>
              {t("assessmentResults.addFinding")}
            </button>
          </div>
          {result.findings.length ? (
            <ul className="profile-list">
              {result.findings.map((finding, index) => (
                <li key={finding.id}>
                  <label className="field">
                    {t("assessmentResults.findingTitle")}
                    <input value={finding.title} onChange={(event) => updateFinding(index, { ...finding, title: event.target.value })} disabled={!canWrite || busy} />
                  </label>
                  <label className="field">
                    {t("assessmentResults.findingDescription")}
                    <textarea value={finding.description} onChange={(event) => updateFinding(index, { ...finding, description: event.target.value })} disabled={!canWrite || busy} />
                  </label>
                  <label className="field">
                    {t("assessmentResults.targetType")}
                    <select
                      value={finding.target_type}
                      onChange={(event) => {
                        const targetType = event.target.value as AssessmentResultFinding["target_type"];
                        const targetId =
                          targetType === "statement-id"
                            ? statementTargetOptions[0]?.statement_id ?? finding.target_id
                            : objectiveTargetOptions[0]?.objective_id ?? finding.target_id;
                        updateFinding(index, { ...finding, target_type: targetType, target_id: targetId });
                      }}
                      disabled={!canWrite || busy}
                    >
                      <option value="statement-id">{t("assessmentResults.target.statement-id")}</option>
                      <option value="objective-id">{t("assessmentResults.target.objective-id")}</option>
                    </select>
                  </label>
                  <label className="field">
                    {t("assessmentResults.targetId")}
                    <select
                      value={finding.target_id}
                      onChange={(event) => updateFinding(index, { ...finding, target_id: event.target.value })}
                      disabled={!canWrite || busy}
                    >
                      {(() => {
                        const options =
                          finding.target_type === "statement-id"
                            ? statementTargetOptions.map((item) => ({
                                id: item.statement_id,
                                title: `${item.statement_id} · ${item.control_id} · ${item.title}`,
                              }))
                            : objectiveTargetOptions.map((item) => ({
                                id: item.objective_id,
                                title: `${item.objective_id} · ${item.control_id}`,
                              }));
                        if (
                          finding.target_id &&
                          !options.some((item) => item.id === finding.target_id)
                        ) {
                          options.unshift({
                            id: finding.target_id,
                            title: t("assessmentResults.targetOutOfScope", {
                              id: finding.target_id,
                            }),
                          });
                        }
                        return options;
                      })().map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.title}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    {t("assessmentResults.findingStatus")}
                    <select
                      value={finding.status}
                      onChange={(event) => updateFinding(index, { ...finding, status: event.target.value as AssessmentResultFinding["status"] })}
                      disabled={!canWrite || busy}
                    >
                      <option value="satisfied">{t("assessmentResults.status.satisfied")}</option>
                      <option value="other">{t("assessmentResults.status.other")}</option>
                      <option value="not-satisfied">{t("assessmentResults.status.not-satisfied")}</option>
                    </select>
                  </label>
                  <fieldset className="repeatable-fields">
                    <legend>{t("assessmentResults.relatedObservations")}</legend>
                    {result.observations.map((observation) => (
                      <label key={observation.id}>
                        <input
                          type="checkbox"
                          checked={finding.related_observation_ids.includes(observation.id)}
                          onChange={(event) =>
                            updateFinding(index, {
                              ...finding,
                              related_observation_ids: event.target.checked
                                ? [...finding.related_observation_ids, observation.id]
                                : finding.related_observation_ids.filter((item) => item !== observation.id),
                            })
                          }
                          disabled={!canWrite || busy}
                        />
                        {observation.title || observation.id}
                      </label>
                    ))}
                  </fieldset>
                  <button type="button" className="secondary" onClick={() => removeFinding(index)} disabled={!canWrite || busy}>
                    {t("assessmentResults.remove")}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("assessmentResults.noFindings")}</p>
          )}
        </section>

        <section className="panel" hidden={tab !== "validation"}>
          <div className="workspace-actions">
            <button type="button" onClick={() => void validateResult()} disabled={busy || dirty}>
              {t("assessmentResults.validate")}
            </button>
            {canWrite ? (
              <button
                type="button"
                onClick={() => void createVersion()}
                disabled={busy || dirty || validationStale || !validation.valid}
              >
                {t("assessmentResults.createVersion")}
              </button>
            ) : null}
          </div>
          <p className="muted">
            {validation.valid
              ? t("assessmentResults.validationPassed")
              : t("assessmentResults.validationIssues")}
          </p>
          {validation.diagnostics.length ? (
            <ul className="diagnostics">
              {validation.diagnostics.map((item, index) => (
                <li key={`${item.code}:${index}`}>
                  <strong>
                    {enumLabel(item.severity)}: {item.code}
                  </strong>
                  {" - "}
                  {item.message}
                  {item.path ? (
                    <p className="muted">
                      {t("assessmentResults.validationPath")}: <span className="mono">{item.path}</span>
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p>{t("assessmentResults.noValidationDiagnostics")}</p>
          )}
          <details>
            <summary>{t("assessmentResults.oscalDetails")}</summary>
            <p className="muted">{t("assessmentResults.oscalDraftCandidate")}</p>
            <pre>{JSON.stringify(validation.oscal_candidate ?? null, null, 2)}</pre>
          </details>
          <h3>{t("systems.versions")}</h3>
          {versions.length ? (
            <ul className="profile-list">
              {versions.map((version) => (
                <li key={version.id}>
                  <strong>
                    {t("common.version")} {version.document_version}
                  </strong>
                  <p className="muted">
                    OSCAL {version.oscal_version} · {date(version.created_at)}
                  </p>
                  <a href={`/bff/tenants/${tenantId}/assessment-results/${result.id}/versions/${version.id}/export`}>
                    {t("systems.exportStoredOscalJson")}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("systems.noImmutableVersions")}</p>
          )}
        </section>

        {canWrite ? <button disabled={busy}>{t("assessmentResults.save")}</button> : null}
      </form>
    </div>
  );
}

function snapshot(result: AssessmentResult) {
  return {
    title: result.title,
    description: result.description,
    reviewed_control_ids: result.reviewed_control_ids,
    observations: result.observations,
    findings: result.findings,
    start: result.start,
    end: result.end,
  };
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


