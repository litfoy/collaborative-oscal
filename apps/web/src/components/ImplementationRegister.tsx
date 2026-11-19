// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useEffect, useState } from "react";

import { bffGet, bffWrite } from "@/lib/bff-client";
import type { Translate } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import type { ControlDetail, Implementation, ImplementationStatus, Paged, Profile, Responsibility } from "@/lib/types";

import { ControlDetailView } from "./ControlDetailView";

type Options = {
  organizations: { id: string; name: string }[];
  people: { id: string; display_name: string | null }[];
};
type Draft = {
  description: string;
  status: ImplementationStatus;
  evidence: string;
  responsibilities: Responsibility[];
  organization_id: string;
};
function statusLabel(status: ImplementationStatus, t: Translate): string {
  switch (status) {
    case "not_started": return t("register.notStartedList");
    case "in_progress": return t("register.inProgressList");
    case "implemented": return t("register.implementedList");
    case "not_applicable": return t("register.notApplicableList");
  }
}
const emptyDraft = (): Draft => ({
  description: "", status: "not_started", evidence: "", responsibilities: [], organization_id: "",
});
const toDraft = (record: Implementation): Draft => ({
  description: record.description, status: record.status, evidence: record.evidence_references.join("\n"),
  responsibilities: record.responsibilities, organization_id: record.organization_id ?? "",
});
export function ImplementationRegister({ tenantId, profile, canWrite, initialControlId, initialImportId = null, onBack }: {
  tenantId: string; profile: Profile; canWrite: boolean; initialControlId: string | null; initialImportId?: string | null; onBack: () => void;
}) {
  const { t, number, date, errorMessage } = useI18n();
  const base = `tenants/${tenantId}`;
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [page, setPage] = useState<Paged<Implementation> | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [record, setRecord] = useState<Implementation | null>(null);
  const [creating, setCreating] = useState(initialControlId !== null && canWrite);
  const imports = profile.imports ?? [{
    id: "", catalog_id: profile.catalog_id, revision_id: profile.revision_id, control_ids: profile.control_ids,
  }];
  const [importId, setImportId] = useState(initialImportId ?? imports[0]?.id ?? "");
  const source = imports.find((item) => item.id === importId) ?? imports[0];
  const [controlId, setControlId] = useState(initialControlId ?? source?.control_ids[0] ?? "");
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [original, setOriginal] = useState<Draft>(emptyDraft);
  const [control, setControl] = useState<ControlDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(original);

  useEffect(() => {
    const controller = new AbortController();
    bffGet<Paged<Implementation>>(`${base}/implementations`, { profile_id: profile.id, limit: 50, offset }, controller.signal)
      .then(setPage).catch((cause: unknown) => { if (!controller.signal.aborted) setError(errorMessage(cause) || t("register.genericError")); });
    return () => controller.abort();
  }, [base, profile.id, offset, reload, errorMessage, t]);

  useEffect(() => {
    const controller = new AbortController();
    bffGet<Options>(`${base}/implementation-options`, undefined, controller.signal)
      .then(setOptions).catch((cause: unknown) => { if (!controller.signal.aborted) setError(errorMessage(cause) || t("register.genericError")); });
    return () => controller.abort();
  }, [base, errorMessage, t]);

  useEffect(() => {
    const controller = new AbortController();
    const path = record ? `${base}/implementations/${record.id}/control` : creating && controlId
      ? `${base}/catalogs/${source.catalog_id}/revisions/${source.revision_id}/controls/${encodeURIComponent(controlId)}` : null;
    if (path) {
      bffGet<ControlDetail>(path, undefined, controller.signal)
        .then((value) => { setControl(value); setDetailError(null); })
        .catch((cause: unknown) => { if (!controller.signal.aborted) setDetailError(errorMessage(cause) || t("register.genericError")); });
    }
    return () => controller.abort();
  }, [base, record, creating, controlId, source.catalog_id, source.revision_id, errorMessage, t]);

  useEffect(() => {
    if (!dirty && !busy) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (!link || link.getAttribute("href")?.startsWith("#") ||
          link.getAttribute("target") === "_blank" || link.hasAttribute("download") ||
          event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      if (busy || !window.confirm(t("register.discardChangesConfirm"))) event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); };
  }, [dirty, busy, t]);

  function canLeave() {
    return !busy && (!dirty || window.confirm(t("register.discardChangesConfirm")));
  }
  function open(item: Implementation) {
    if (!canLeave()) return;
    setRecord(item); setCreating(false); setControl(null); setDetailError(null);
    const value = toDraft(item); setDraft(value); setOriginal(value); setError(null);
  }
  function newRecord() {
    if (!canLeave()) return;
    const value = emptyDraft(); setDraft(value); setOriginal(value);
    setRecord(null); setCreating(true); setControl(null); setDetailError(null); setError(null);
  }
  async function save() {
    setBusy(true); setError(null);
    const info = {
      description: draft.description, status: draft.status,
      evidence_references: draft.evidence.split("\n").map((s) => s.trim()).filter(Boolean),
      responsibilities: draft.responsibilities,
    };
    try {
      const saved = record
        ? await bffWrite<Implementation>("PUT", `${base}/implementations/${record.id}`, info)
        : await bffWrite<Implementation>("POST", `${base}/implementations`, {
          ...info, organization_id: draft.organization_id || null, profile_id: profile.id,
          catalog_id: source.catalog_id, revision_id: source.revision_id, oscal_control_id: controlId,
          ...(importId ? { profile_import_id: importId } : {}),
        });
      setRecord(saved); setCreating(false);
      const value = toDraft(saved); setDraft(value); setOriginal(value);
      setReload((n) => n + 1);
    } catch (cause) { setError(errorMessage(cause) || t("register.genericError")); }
    finally { setBusy(false); }
  }
  function updateResponsibility(index: number, patch: Partial<Responsibility>) {
    setDraft({ ...draft, responsibilities: draft.responsibilities.map((r, i) => i === index ? { ...r, ...patch } : r) });
  }

  return <div className="profile-workspace">
    <header className="panel">
      <button type="button" className="secondary" onClick={() => { if (canLeave()) onBack(); }}>{t("register.backToProfile")}</button>
      <h2>{t("register.title")}</h2>
      <p>{t("register.description")}</p>
      {error ? <p role="alert" className="alert">{error}</p> : null}
    </header>
    <section className="panel">
      <h3>{t("register.implementationsFor", { name: profile.title })}</h3>
      {canWrite ? <button type="button" onClick={newRecord}>{t("register.create")}</button> : null}
      {!page ? <p>{t("register.loading")}</p> : page.items.length === 0 ? <p>{t("register.emptyPage")}</p> :
        <ul>{page.items.map((item) => <li key={item.id}>
          <button type="button" className="secondary" onClick={() => open(item)}>
            {item.oscal_control_id} · {statusLabel(item.status, t)} · {t("register.revisionPrefix")} {item.revision_id} · {item.organization_id
              ? options?.organizations.find((org) => org.id === item.organization_id)?.name ?? item.organization_id
              : t("register.tenant")} · {item.id}
          </button>
        </li>)}</ul>}
      {page ? <div className="workspace-actions">
        <button type="button" className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{t("register.previous")}</button>
        <span>{t("register.pagination", { start: number(offset + 1), end: number(Math.min(offset + page.items.length, page.total)), total: number(page.total) })}</span>
        <button type="button" className="secondary" disabled={offset + page.items.length >= page.total} onClick={() => setOffset(offset + 50)}>{t("register.next")}</button>
      </div> : null}
    </section>
    {record || creating ? <section className="panel">
      <h3>{t("register.normativeRequirement")}</h3>
      {creating && imports.length > 1 ? <label className="field">{t("register.sourceImport")}
        <select value={importId} onChange={(event) => {
          if (!canLeave()) return;
          const next = imports.find((item) => item.id === event.target.value);
          setImportId(event.target.value); setControlId(next?.control_ids[0] ?? "");
          setControl(null); setDetailError(null);
          const value = emptyDraft(); setDraft(value); setOriginal(value);
        }}>
          {imports.map((item) => <option key={item.id} value={item.id}>{t("register.catalogRevisionImport", { catalog: item.catalog_id, revision: item.revision_id, import: item.id })}</option>)}
        </select>
      </label> : null}
      {creating ? <label className="field">{t("register.selectedRequirement")}
        <select value={controlId} onChange={(event) => {
          if (!canLeave()) return;
          setControlId(event.target.value); setControl(null); setDetailError(null);
          const value = emptyDraft(); setDraft(value); setOriginal(value);
        }}>
          {source.control_ids.map((id) => <option key={id} value={id}>{id}</option>)}
        </select>
      </label> : <p>{t("register.originalRevision")} <span className="mono">{record?.revision_id}</span></p>}
      {detailError ? <p role="alert" className="alert">{detailError}</p> : control
        ? <ControlDetailView control={control} presentation="profile" /> : <p>{t("register.requirementLoading")}</p>}
      <h3>{t("register.implementationInformation")} {canWrite ? `— ${t("register.editable")}` : `— ${t("register.readOnly")}`}</h3>
      {record ? <p>{t("register.lastModified", { id: record.id, date: date(record.updated_at), user: record.updated_by })}</p> : null}
      <fieldset disabled={!canWrite || busy} className="profile-form">
        <label className="field">{t("register.scope")}
          <select value={draft.organization_id} disabled={!creating} onChange={(event) => setDraft({ ...draft, organization_id: event.target.value })}>
            <option value="">{t("register.tenantScope")}</option>
            {draft.organization_id && !options?.organizations.some((org) => org.id === draft.organization_id)
              ? <option value={draft.organization_id}>{draft.organization_id}</option> : null}
            {options?.organizations.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}
          </select>
        </label>
        <label className="field">{t("register.descriptionLabel")}
          <textarea maxLength={50000} rows={5} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
        </label>
        <label className="field">{t("register.status")}
          <select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as ImplementationStatus })}>
            <option value="not_started">{t("register.notStarted")}</option><option value="in_progress">{t("register.inProgress")}</option>
            <option value="implemented">{t("register.implemented")}</option><option value="not_applicable">{t("register.notApplicable")}</option>
          </select>
        </label>
        <label className="field">{t("register.evidenceReferences")}
          <textarea rows={3} value={draft.evidence} onChange={(event) => setDraft({ ...draft, evidence: event.target.value })} />
        </label>
        <h4>{t("register.responsibilities")}</h4>
        {draft.responsibilities.map((r, i) => <div key={i}>
          <label className="field">{t("register.responsibility", { number: number(i + 1) })}
            <select value={r.kind} onChange={(event) => updateResponsibility(i, { kind: event.target.value as Responsibility["kind"] })}>
              <option value="accountable">{t("register.accountable")}</option><option value="responsible">{t("register.responsible")}</option><option value="participant">{t("register.participant")}</option>
            </select>
          </label>
          <label className="field">{t("register.person")}
            <select value={r.user_id ?? ""} onChange={(event) => updateResponsibility(i, { user_id: event.target.value || null })}>
              <option value="">{t("register.noPerson")}</option>
              {r.user_id && !options?.people.some((person) => person.id === r.user_id) ? <option value={r.user_id}>{r.user_id} {t("register.inactiveUnavailable")}</option> : null}
              {options?.people.map((person) => <option key={person.id} value={person.id}>{person.display_name ?? person.id}</option>)}
            </select>
          </label>
          <label className="field">{t("register.role")}
            <input maxLength={255} value={r.role} onChange={(event) => updateResponsibility(i, { role: event.target.value })} />
          </label>
          <button type="button" className="secondary" onClick={() => setDraft({ ...draft, responsibilities: draft.responsibilities.filter((_, n) => n !== i) })}>{t("register.removeResponsibility")}</button>
        </div>)}
        <button type="button" className="secondary" onClick={() => setDraft({ ...draft, responsibilities: [...draft.responsibilities, { kind: "responsible", user_id: null, role: "" }] })}>{t("register.addResponsibility")}</button>
        <button type="button" disabled={!controlId && !record} onClick={() => void save()}>{busy ? t("register.saving") : t("register.save")}</button>
      </fieldset>
    </section> : null}
  </div>;
}
