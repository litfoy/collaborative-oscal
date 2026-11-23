// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { Fragment, useMemo, useState } from "react";

import { bffGet } from "@/lib/bff-client";
import type { Translate } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import type {
  ComplianceExplorerControlItem,
  ComplianceExplorerPage,
  InformationSystem,
  Profile,
} from "@/lib/types";
import { ComplianceExplorerMeasuresView } from "./ComplianceExplorerMeasuresView";

const PAGE_SIZE = 20;

export function ComplianceExplorerRequirementsView({
  tenantId,
  systems,
  profiles,
}: {
  tenantId: string;
  systems: InformationSystem[];
  profiles: Profile[];
}) {
  const { t, number, enumLabel, errorMessage } = useI18n();
  const [selectedSystemId, setSelectedSystemId] = useState("");
  const [selectedProfileIds, setSelectedProfileIds] = useState<string[]>([]);
  const [applied, setApplied] = useState<{ systemId: string; profileIds: string[] } | null>(null);
  const [page, setPage] = useState<ComplianceExplorerPage | null>(null);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"requirements" | "measures">("requirements");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const sortedSystems = useMemo(
    () => [...systems].sort((a, b) => a.name.localeCompare(b.name)),
    [systems],
  );
  const sortedProfiles = useMemo(
    () => [...profiles].sort((a, b) => a.title.localeCompare(b.title)),
    [profiles],
  );

  async function loadPage(offset: number, systemId: string, profileIds: string[]) {
    setLoading(true);
    setError("");
    try {
      const response = await bffGet<ComplianceExplorerPage>(
        `tenants/${tenantId}/systems/${systemId}/compliance-explorer`,
        {
          limit: PAGE_SIZE,
          offset,
          profile_id: profileIds,
        },
      );
      setPage(response);
      setExpandedKey(null);
    } catch (reason) {
      setError(errorMessage(reason));
      setPage(null);
    } finally {
      setLoading(false);
    }
  }

  async function applySelection() {
    if (!selectedSystemId) {
      setError(t("complianceExplorer.selectionRequired"));
      return;
    }
    if (selectedProfileIds.length < 1 || selectedProfileIds.length > 5) {
      setError(t("complianceExplorer.profileSelectionInvalid"));
      return;
    }
    const next = { systemId: selectedSystemId, profileIds: selectedProfileIds };
    setApplied(next);
    await loadPage(0, next.systemId, next.profileIds);
  }

  async function changePage(nextOffset: number) {
    if (!applied) return;
    await loadPage(nextOffset, applied.systemId, applied.profileIds);
  }

  function toggleProfile(profileId: string) {
    setSelectedProfileIds((current) => {
      if (current.includes(profileId)) return current.filter((id) => id !== profileId);
      if (current.length >= 5) return current;
      return [...current, profileId];
    });
  }

  const pages = page ? Math.max(1, Math.ceil(page.total / page.limit)) : 1;
  const pageNumber = page ? Math.floor(page.offset / page.limit) + 1 : 1;
  const profileSelectionDiffers = applied
    ? applied.profileIds.length !== selectedProfileIds.length ||
      applied.profileIds.some((profileId) => !selectedProfileIds.includes(profileId))
    : false;
  const draftDiffers = applied
    ? applied.systemId !== selectedSystemId || profileSelectionDiffers
    : false;
  const draftSystem = sortedSystems.find((system) => system.id === selectedSystemId);
  const draftProfiles = sortedProfiles
    .filter((profile) => selectedProfileIds.includes(profile.id))
    .map((profile) => profile.title);

  return (
    <div className="workspace">
      <h1>{t("complianceExplorer.title")}</h1>
      <p className="muted">{t("complianceExplorer.intro")}</p>
      <p className="muted">{t("complianceExplorer.scopeNote")}</p>

      <section className="panel stack ce-selection-panel" aria-label={t("complianceExplorer.selectionTitle")}>
        <h2>{t("complianceExplorer.selectionTitle")}</h2>
        <p className="muted">{t("complianceExplorer.profileHelp")}</p>

        <div className="ce-selection-grid">
          <label className="field">
            {t("complianceExplorer.system")}
            <select
              value={selectedSystemId}
              onChange={(event) => setSelectedSystemId(event.target.value)}
              disabled={loading || sortedSystems.length === 0}
            >
              <option value="">{t("complianceExplorer.selectSystem")}</option>
              {sortedSystems.map((system) => (
                <option key={system.id} value={system.id}>
                  {system.name}
                </option>
              ))}
            </select>
          </label>

          <fieldset className="ce-profile-fieldset">
            <legend>{t("complianceExplorer.profiles")}</legend>
            <p className="muted">{t("complianceExplorer.selectProfiles")}</p>
            <p className="muted" role="status" aria-live="polite">
              {t("complianceExplorer.selectedProfilesCount", {
                count: number(selectedProfileIds.length),
                max: number(5),
              })}
            </p>
            <div className="ce-profile-list" role="group" aria-label={t("complianceExplorer.profiles")}>
              {sortedProfiles.map((profile) => {
                const checked = selectedProfileIds.includes(profile.id);
                const disabled = loading || (!checked && selectedProfileIds.length >= 5);
                return (
                  <label key={profile.id} className="selection-row">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggleProfile(profile.id)}
                    />
                    <span>{profile.title}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        </div>

        <section className="panel" aria-label={t("complianceExplorer.draftContext")}>
          <h3>{t("complianceExplorer.draftContext")}</h3>
          <dl className="meta-list">
            <dt>{t("complianceExplorer.draftSystem")}</dt>
            <dd>{draftSystem?.name ?? t("complianceExplorer.noneSelected")}</dd>
            <dt>{t("complianceExplorer.draftProfiles")}</dt>
            <dd>
              {draftProfiles.length > 0
                ? draftProfiles.join(", ")
                : t("complianceExplorer.noneSelected")}
            </dd>
          </dl>
        </section>

        <div className="workspace-actions ce-selection-actions">
          <button
            type="button"
            onClick={() => void applySelection()}
            disabled={loading || sortedSystems.length === 0 || sortedProfiles.length === 0}
          >
            {t("complianceExplorer.apply")}
          </button>
        </div>
      </section>

      {sortedSystems.length === 0 ? <div className="empty">{t("complianceExplorer.emptySystems")}</div> : null}
      {sortedProfiles.length === 0 ? <div className="empty">{t("complianceExplorer.emptyProfiles")}</div> : null}
      {loading ? <p role="status">{t("complianceExplorer.loading")}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!applied && !loading && !error ? (
        <div className="empty">{t("complianceExplorer.selectionRequired")}</div>
      ) : null}

      {applied && page ? (
        <section className="panel ce-applied-context" role="status" aria-label={t("complianceExplorer.appliedContext")}>
          <h2>{t("complianceExplorer.appliedContext")}</h2>
          <dl className="meta-list">
            <dt>{t("complianceExplorer.appliedSystem")}</dt>
            <dd>{page.system.name}</dd>
            <dt>{t("complianceExplorer.appliedProfiles")}</dt>
            <dd>{page.profiles.map((profile) => profile.title).join(", ")}</dd>
            <dt>{t("complianceExplorer.selectedProfilesCountLabel")}</dt>
            <dd>{number(page.profiles.length)}</dd>
          </dl>
          {draftDiffers ? <p className="muted">{t("complianceExplorer.draftDiffers")}</p> : null}
        </section>
      ) : null}

      {applied && page ? (
        <div className="workspace-actions ce-view-switch" role="group" aria-label={t("complianceExplorer.viewSwitch")}>
          <button
            type="button"
            className={viewMode === "requirements" ? "" : "secondary"}
            aria-pressed={viewMode === "requirements"}
            onClick={() => setViewMode("requirements")}
          >
            {t("complianceExplorer.requirementsView")}
          </button>
          <button
            type="button"
            className={viewMode === "measures" ? "" : "secondary"}
            aria-pressed={viewMode === "measures"}
            onClick={() => setViewMode("measures")}
          >
            {t("complianceExplorer.measuresView")}
          </button>
        </div>
      ) : null}

      {applied && page && page.items.length === 0 && !loading ? (
        <div className="empty">{t("complianceExplorer.emptyResult")}</div>
      ) : null}

      {applied && page && page.items.length > 0 && viewMode === "requirements" ? (
        <>
          <p className="muted" role="status">
            {t("complianceExplorer.pageSummary", {
              count: number(page.items.length),
              total: number(page.total),
            })}
          </p>
          <table id="compliance-explorer-results" className="ce-requirements-table" aria-label={t("complianceExplorer.tableLabel")}>
            <thead>
              <tr>
                <th>{t("complianceExplorer.control")}</th>
                <th>{t("complianceExplorer.memberships")}</th>
                <th>{t("complianceExplorer.implementations")}</th>
                <th>{t("complianceExplorer.workflowStatuses")}</th>
                <th>{t("complianceExplorer.oscalStatuses")}</th>
                <th>{t("complianceExplorer.details")}</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((item) => {
                const key = controlKey(item);
                const expanded = expandedKey === key;
                return (
                  <Fragment key={key}>
                    <tr>
                      <td>
                        <p className="ce-control-heading">
                          <strong className="mono">{item.reference.oscal_control_id}</strong>
                          <span>{item.title}</span>
                        </p>
                        <div className="muted mono">
                          {t("complianceExplorer.source")}: {item.reference.catalog_id} / {item.reference.revision_id}
                        </div>
                      </td>
                      <td>
                        {item.memberships.map((membership) => membership.profile_title).join(", ")}
                      </td>
                      <td>{number(item.implementations.length)}</td>
                      <td>{summarizeWorkflowStatuses(item, t, enumLabel)}</td>
                      <td>{summarizeOscalStatuses(item, t, enumLabel)}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary"
                          aria-expanded={expanded}
                          aria-controls={`ce-details-${key}`}
                          onClick={() => setExpandedKey(expanded ? null : key)}
                        >
                          {t("complianceExplorer.toggleDetails", {
                            control: item.reference.oscal_control_id,
                          })}
                        </button>
                      </td>
                    </tr>
                    {expanded ? (
                      <tr id={`ce-details-${key}`}>
                        <td colSpan={6}>{renderDetails(item, t, enumLabel)}</td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>

        </>
      ) : null}

      {applied && page && page.items.length > 0 && viewMode === "measures" ? (
        <div id="compliance-explorer-results">
          <ComplianceExplorerMeasuresView page={page} />
        </div>
      ) : null}
      {applied && page && page.items.length > 0 && page.total > page.limit ? (
        <nav className="pagination" aria-label={t("complianceExplorer.pageLabel")}>
          <button
            type="button"
            className="secondary"
            onClick={() => void changePage(Math.max(0, page.offset - page.limit))}
            disabled={loading || page.offset === 0}
          >
            {t("common.previous")}
          </button>
          <span>{t("common.page", { page: number(pageNumber), pages: number(pages) })}</span>
          <button
            type="button"
            className="secondary"
            onClick={() => void changePage(page.offset + page.limit)}
            disabled={loading || page.offset + page.limit >= page.total}
          >
            {t("common.next")}
          </button>
        </nav>
      ) : null}
    </div>
  );
}

function controlKey(item: ComplianceExplorerControlItem): string {
  const { catalog_id: catalogId, revision_id: revisionId, oscal_control_id: oscalControlId } =
    item.reference;
  return `${catalogId}:${revisionId}:${oscalControlId}`;
}

function renderDetails(
  item: ComplianceExplorerControlItem,
  t: Translate,
  enumLabel: (value: string) => string,
) {
  if (item.implementations.length === 0) {
    return <p>{t("complianceExplorer.noImplementation")}</p>;
  }
  return (
    <div className="stack">
      <dl className="meta-list">
        <dt>{t("complianceExplorer.source")}</dt>
        <dd className="mono">
          {item.reference.catalog_id} / {item.reference.revision_id} / {item.reference.oscal_control_id}
        </dd>
        <dt>{t("complianceExplorer.memberships")}</dt>
        <dd>{item.memberships.map((membership) => membership.profile_title).join(", ")}</dd>
      </dl>
      {item.implementations.map((implementation) => (
        <div key={implementation.id} className="panel">
          <dl className="meta-list">
            <dt>{t("complianceExplorer.implementationId")}</dt>
            <dd className="mono">{implementation.id}</dd>
            <dt>{t("complianceExplorer.workflowStatus")}</dt>
            <dd>{enumLabel(implementation.status)}</dd>
            <dt>{t("complianceExplorer.oscalStatus")}</dt>
            <dd>
              {implementation.oscal_implementation_status
                ? enumLabel(implementation.oscal_implementation_status)
                : t("complianceExplorer.na")}
            </dd>
            <dt>{t("complianceExplorer.oscalExplanation")}</dt>
            <dd>{implementation.oscal_status_explanation ?? t("complianceExplorer.na")}</dd>
            <dt>{t("complianceExplorer.provenance")}</dt>
            <dd className="mono">
              {implementation.profile_id ?? t("complianceExplorer.na")} /{" "}
              {implementation.profile_import_id ?? t("complianceExplorer.na")}
            </dd>
            <dt>{t("complianceExplorer.component")}</dt>
            <dd>
              {implementation.system_component
                ? `${implementation.system_component.title ?? t("complianceExplorer.na")} (${implementation.system_component.id})`
                : t("complianceExplorer.notLinked")}
            </dd>
          </dl>
        </div>
      ))}
    </div>
  );
}

function summarizeWorkflowStatuses(
  item: ComplianceExplorerControlItem,
  t: Translate,
  enumLabel: (value: string) => string,
) {
  if (item.implementations.length === 0) {
    return t("complianceExplorer.noImplementation");
  }
  return [...new Set(item.implementations.map((implementation) => enumLabel(implementation.status)))].join(", ");
}

function summarizeOscalStatuses(
  item: ComplianceExplorerControlItem,
  t: Translate,
  enumLabel: (value: string) => string,
) {
  if (item.implementations.length === 0) {
    return t("complianceExplorer.na");
  }
  return [...new Set(item.implementations.map((implementation) => (
    implementation.oscal_implementation_status
      ? enumLabel(implementation.oscal_implementation_status)
      : t("complianceExplorer.na")
  )))].join(", ");
}
