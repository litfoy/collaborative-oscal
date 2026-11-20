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

  return (
    <div className="workspace">
      <h1>{t("complianceExplorer.title")}</h1>
      <p className="muted">{t("complianceExplorer.intro")}</p>
      <p className="muted">{t("complianceExplorer.scopeNote")}</p>

      <section className="panel stack" aria-label={t("complianceExplorer.title")}>
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

        <fieldset>
          <legend>{t("complianceExplorer.profiles")}</legend>
          <p className="muted">{t("complianceExplorer.profileHelp")}</p>
          <p className="muted">
            {t("complianceExplorer.selectProfiles")} ({number(selectedProfileIds.length)}/5)
          </p>
          <div className="stack">
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

        <div className="workspace-actions">
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

      {applied && page && page.items.length === 0 && !loading ? (
        <div className="empty">{t("complianceExplorer.emptyResult")}</div>
      ) : null}

      {applied && page && page.items.length > 0 ? (
        <>
          <p className="muted" role="status">
            {t("complianceExplorer.pageSummary", {
              count: number(page.items.length),
              total: number(page.total),
            })}
          </p>
          <table aria-label={t("complianceExplorer.tableLabel")}>
            <thead>
              <tr>
                <th>{t("complianceExplorer.control")}</th>
                <th>{t("complianceExplorer.memberships")}</th>
                <th>{t("complianceExplorer.implementations")}</th>
                <th>{t("complianceExplorer.statuses")}</th>
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
                        <strong>{item.reference.oscal_control_id}</strong> - {item.title}
                        <div className="muted mono">
                          {t("complianceExplorer.source")}: {item.reference.catalog_id} / {item.reference.revision_id}
                        </div>
                      </td>
                      <td>{item.memberships.map((membership) => membership.profile_title).join(", ")}</td>
                      <td>{number(item.implementations.length)}</td>
                      <td>
                        {item.implementations.length === 0 ? (
                          <span>{t("complianceExplorer.noImplementation")}</span>
                        ) : (
                          item.implementations.map((implementation) => (
                            <div key={implementation.id}>
                              {enumLabel(implementation.status)}
                              {implementation.oscal_implementation_status
                                ? ` / ${enumLabel(implementation.oscal_implementation_status)}`
                                : ""}
                            </div>
                          ))
                        )}
                      </td>
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
                        <td colSpan={5}>{renderDetails(item, t, enumLabel)}</td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>

          {page.total > page.limit ? (
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
        </>
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




