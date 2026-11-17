"use client";

import { useI18n } from "@/lib/i18n/provider";
import type { SystemComponent } from "@/lib/types";

interface SnapshotViewProps {
  tenantId: string;
  systemId: string;
  systemName: string;
  component: SystemComponent;
  snapshot: Record<string, unknown>;
}

interface SnapshotMetadata {
  title?: string;
  version?: string;
  oscalVersion?: string;
  lastModified?: string;
}

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.length > 0) : [];
}

function readMetadata(root: Record<string, unknown>): SnapshotMetadata {
  const metadata = asObject(root.metadata);
  if (!metadata) return {};
  return {
    title: asString(metadata.title) ?? undefined,
    version: asString(metadata.version) ?? undefined,
    oscalVersion: asString(metadata["oscal-version"]) ?? undefined,
    lastModified: asString(metadata["last-modified"]) ?? undefined,
  };
}

function readGuidance(component: Record<string, unknown>) {
  const controlImplementations = Array.isArray(component["control-implementations"])
    ? component["control-implementations"].map(asObject).filter((item): item is Record<string, unknown> => Boolean(item))
    : [];
  const controls = controlImplementations.flatMap((implementation) => {
    const implementedRequirements = Array.isArray(implementation["implemented-requirements"])
      ? implementation["implemented-requirements"].map(asObject).filter((item): item is Record<string, unknown> => Boolean(item))
      : [];
    return implementedRequirements.map((requirement) => ({
      controlId: asString(requirement["control-id"]),
      description: asString(requirement.description),
      statements: Array.isArray(requirement.statements)
        ? requirement.statements
            .map(asObject)
            .filter((item): item is Record<string, unknown> => Boolean(item))
            .map((statement) => asString(statement.description))
            .filter((item): item is string => Boolean(item))
        : [],
    }));
  });
  return controls;
}

export function SystemComponentSnapshotView({
  tenantId,
  systemId,
  systemName,
  component,
  snapshot,
}: SnapshotViewProps) {
  const { t, date, enumLabel, number } = useI18n();
  const root = asObject(snapshot["component-definition"]);
  const sourceComponent = root && Array.isArray(root.components)
    ? root.components.map(asObject).find((item): item is Record<string, unknown> => Boolean(item))
    : null;

  if (!root || !sourceComponent || !component.source_snapshot_id || !component.source_component_uuid) {
    return (
      <div className="workspace">
        <p role="alert" className="alert">{t("systems.snapshotUnavailable")}</p>
        <a href={`/t/${tenantId}/systems/${systemId}`}>{t("systems.backToSystemComponents")}</a>
      </div>
    );
  }

  const metadata = readMetadata(root);
  const guidance = readGuidance(sourceComponent);
  const sourceExportHref = `/bff/tenants/${tenantId}/component-definition-snapshots/${component.source_snapshot_id}/components/${component.source_component_uuid}/export`;
  const links = Array.isArray(sourceComponent.links)
    ? sourceComponent.links
        .map(asObject)
        .filter((item): item is Record<string, unknown> => item !== null)
        .filter((item) => Boolean(asString(item.href)))
        .map((item) => ({ href: asString(item.href)!, text: asString(item.text), rel: asString(item.rel) }))
    : [];
  const sourceType = asString(sourceComponent.type);
  const sourceStatus = asObject(sourceComponent.status);
  const sourceStatusState = sourceStatus ? asString(sourceStatus.state) : null;

  return (
    <div className="workspace">
      <nav className="breadcrumbs" aria-label={t("systems.snapshotBreadcrumb")}>
        <a href={`/t/${tenantId}/systems`}>{t("systems.backToSystems")}</a> › {" "}
        <a href={`/t/${tenantId}/systems/${systemId}`}>{systemName}</a> › {" "}
        <span aria-current="page">{t("systems.sourceSnapshotViewTitle")}</span>
      </nav>
      <section className="panel">
        <h1>{component.component.title}</h1>
        <p className="source-banner">{t("systems.snapshotImmutableNotice")}</p>
        <dl className="meta-list">
          <dt>{t("systems.snapshotReference")}</dt>
          <dd className="mono">{component.source_snapshot_id}</dd>
          <dt>{t("systems.componentUuid")}</dt>
          <dd className="mono">{component.source_component_uuid}</dd>
          <dt>{t("systems.componentType")}</dt>
          <dd>{sourceType === "process-procedure" ? t("systems.processProcedure") : sourceType ? enumLabel(sourceType) : t("systems.notSet")}</dd>
          <dt>{t("systems.componentOperationalStatus")}</dt>
          <dd>{sourceStatusState ? enumLabel(sourceStatusState) : t("systems.notSet")}</dd>
          {metadata.title ? <><dt>{t("systems.sourceDefinitionTitle")}</dt><dd>{metadata.title}</dd></> : null}
          {metadata.version ? <><dt>{t("systems.sourceDefinitionVersion")}</dt><dd>{metadata.version}</dd></> : null}
          {metadata.oscalVersion ? <><dt>{t("systems.oscalVersion")}</dt><dd>{metadata.oscalVersion}</dd></> : null}
          {metadata.lastModified ? <><dt>{t("systems.lastModified")}</dt><dd>{date(metadata.lastModified)}</dd></> : null}
        </dl>
        {asString(sourceComponent.description) ? (
          <section>
            <h2>{t("systems.actualDeploymentDescription")}</h2>
            <p className="prose">{asString(sourceComponent.description)}</p>
          </section>
        ) : null}
        {asString(sourceComponent.purpose) ? (
          <section>
            <h2>{t("systems.purposeOptional")}</h2>
            <p className="prose">{asString(sourceComponent.purpose)}</p>
          </section>
        ) : null}
        <section>
          <h2>{t("systems.implementationGuidance")}</h2>
          {guidance.length ? (
            <ul className="profile-list">
              {guidance.map((item, index) => (
                <li key={`${item.controlId ?? "control"}-${index}`}>
                  <strong>{item.controlId ?? t("systems.unknown")}</strong>
                  {item.description ? <p className="prose">{item.description}</p> : null}
                  {item.statements.length ? <p className="muted">{t("systems.guidanceStatements", { count: number(item.statements.length) })}</p> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">{t("systems.noImplementationGuidance")}</p>
          )}
        </section>
        {links.length ? (
          <section>
            <h2>{t("systems.sourceReferences")}</h2>
            <ul>
              {links.map((link, index) => (
                <li key={index}>
                  <a href={link.href}>{link.text ?? link.href}</a>
                  {link.rel ? <span className="muted"> ({link.rel})</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <details className="technical-details">
          <summary>{t("systems.exportStoredOscalJson")}</summary>
          <p className="muted">{t("systems.rawSnapshotJsonNotice")}</p>
          <a className="button secondary" href={sourceExportHref}>{t("systems.openRawSnapshotJson")}</a>
        </details>
      </section>
    </div>
  );
}



