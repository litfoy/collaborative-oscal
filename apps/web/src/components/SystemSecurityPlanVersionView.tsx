// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

"use client";

import { useI18n } from "@/lib/i18n/provider";
import type { SystemSecurityPlanVersion } from "@/lib/types";

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asObjects(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.map(asObject).filter((item): item is Record<string, unknown> => Boolean(item))
    : [];
}

interface ParsedContribution {
  componentUuid: string | null;
  description: string | null;
  status: string | null;
}

interface ParsedRequirement {
  controlId: string | null;
  description: string | null;
  contributions: ParsedContribution[];
}

function parseSnapshot(snapshot: Record<string, unknown>) {
  const root = asObject(snapshot["system-security-plan"]);
  if (!root) {
    return {
      metadata: null,
      requirements: [] as ParsedRequirement[],
      componentTitleByUuid: new Map<string, string>(),
    };
  }

  const metadata = asObject(root.metadata);
  const componentTitleByUuid = new Map<string, string>();
  asObjects(asObject(root["system-implementation"])?.components).forEach((component) => {
    const uuid = asString(component.uuid);
    const title = asString(component.title);
    if (uuid && title) componentTitleByUuid.set(uuid, title);
  });

  const implementedRequirements = asObjects(
    asObject(root["control-implementation"])?.["implemented-requirements"],
  );
  const requirements = implementedRequirements.map((requirement) => {
    const nested = asObjects(requirement["by-components"]);
    const statements = asObjects(requirement.statements).flatMap((statement) =>
      asObjects(statement["by-components"]),
    );
    const contributions = [...nested, ...statements].map((entry) => ({
      componentUuid: asString(entry["component-uuid"]),
      description: asString(entry.description),
      status: asString(asObject(entry.status)?.state),
    }));
    return {
      controlId: asString(requirement["control-id"]),
      description: asString(requirement.description),
      contributions,
    };
  });

  return { metadata, requirements, componentTitleByUuid };
}

export function SystemSecurityPlanVersionView({
  tenantId,
  systemId,
  systemName,
  planId,
  planTitle,
  version,
  snapshot,
}: {
  tenantId: string;
  systemId: string;
  systemName: string;
  planId: string;
  planTitle: string;
  version: SystemSecurityPlanVersion;
  snapshot: Record<string, unknown>;
}) {
  const { t, date, enumLabel, number } = useI18n();
  const { metadata, requirements, componentTitleByUuid } = parseSnapshot(snapshot);
  const historicalTitle = asString(metadata?.title) ?? planTitle;
  const historicalVersion = asString(metadata?.version) ?? version.document_version;

  return (
    <div className="workspace">
      <nav className="breadcrumbs" aria-label={t("systems.snapshotBreadcrumb")}>
        <a href={`/t/${tenantId}/systems`}>{t("systems.backToSystems")}</a> {" > "}
        <a href={`/t/${tenantId}/systems/${systemId}`}>{systemName}</a> {" > "}
        <a href={`/t/${tenantId}/systems/${systemId}/system-security-plans/${planId}`}>{planTitle}</a> {" > "}
        <span aria-current="page">{t("systems.historicalVersionView")}</span>
      </nav>
      <section className="panel">
        <h1>{historicalTitle}</h1>
        <p className="source-banner">{t("systems.historicalSnapshotNotice")}</p>
        <dl className="meta-list">
          <dt>{t("common.version")}</dt>
          <dd>{historicalVersion}</dd>
          <dt>{t("systems.oscalVersion")}</dt>
          <dd>{version.oscal_version}</dd>
          <dt>{t("systems.lastModified")}</dt>
          <dd>
            <time dateTime={version.last_modified}>{date(version.last_modified)}</time>
          </dd>
          <dt>{t("systems.stableSspVersionReference")}</dt>
          <dd className="mono">{version.id}</dd>
        </dl>
      </section>
      <section className="panel">
        <h2>{t("systems.requirementContributions")}</h2>
        {requirements.length ? (
          <ul className="profile-list">
            {requirements.map((requirement, index) => (
              <li key={`${requirement.controlId ?? "control"}-${index}`}>
                <strong>{requirement.controlId ?? t("systems.unknown")}</strong>
                {requirement.description ? <p className="prose">{requirement.description}</p> : null}
                <p className="muted">
                  {t("systems.contributionCount", {
                    count: number(requirement.contributions.length),
                  })}
                </p>
                {requirement.contributions.length ? (
                  <ul>
                    {requirement.contributions.map((contribution, contributionIndex) => {
                      const title = contribution.componentUuid
                        ? componentTitleByUuid.get(contribution.componentUuid)
                        : null;
                      return (
                        <li key={`${contribution.componentUuid ?? "component"}-${contributionIndex}`}>
                          {title ?? contribution.componentUuid ?? t("systems.componentUnavailable")}
                          {contribution.status ? ` · ${enumLabel(contribution.status)}` : ""}
                          {contribution.description ? ` · ${contribution.description}` : ""}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("systems.noHistoricalRequirements")}</p>
        )}
      </section>
      <details className="technical-details">
        <summary>{t("systems.versionTechnicalActions")}</summary>
        <div className="workspace-actions">
          <a
            className="button secondary"
            href={`/bff/tenants/${tenantId}/system-security-plans/${planId}/versions/${version.id}/export`}
          >
            {t("systems.exportStoredOscalJson")}
          </a>
          <a
            href={`/bff/tenants/${tenantId}/system-security-plans/${planId}/versions/${version.id}`}
            className="muted"
          >
            {t("systems.stableSspVersionReference")}
          </a>
        </div>
      </details>
    </div>
  );
}



