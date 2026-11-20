// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import type { Translate } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import type { ComplianceExplorerControlItem, ComplianceExplorerPage } from "@/lib/types";

interface MeasuresControlAssociation {
  control: ComplianceExplorerControlItem;
  implementationIds: string[];
  statuses: string[];
  oscalStatuses: (string | null)[];
  provenance: { profileId: string | null; importId: string | null }[];
}

interface MeasuresComponentGroup {
  id: string;
  title: string | null;
  controls: MeasuresControlAssociation[];
}

export function ComplianceExplorerMeasuresView({ page }: { page: ComplianceExplorerPage }) {
  const { t, number, enumLabel } = useI18n();
  const componentGroups = new Map<string, MeasuresComponentGroup>();
  const unlinked: MeasuresControlAssociation[] = [];
  const controlsWithoutImplementations: ComplianceExplorerControlItem[] = [];

  for (const control of page.items) {
    if (control.implementations.length === 0) {
      controlsWithoutImplementations.push(control);
    }

    for (const implementation of control.implementations) {
      const association: MeasuresControlAssociation = {
        control,
        implementationIds: [implementation.id],
        statuses: [implementation.status],
        oscalStatuses: [implementation.oscal_implementation_status],
        provenance: [{
          profileId: implementation.profile_id,
          importId: implementation.profile_import_id,
        }],
      };

      if (implementation.system_component_id === null || implementation.system_component === null) {
        const existing = unlinked.find((item) =>
          item.control.reference.catalog_id === control.reference.catalog_id
          && item.control.reference.revision_id === control.reference.revision_id
          && item.control.reference.oscal_control_id === control.reference.oscal_control_id
        );
        if (existing) {
          existing.implementationIds.push(...association.implementationIds);
          existing.statuses.push(...association.statuses);
          existing.oscalStatuses.push(...association.oscalStatuses);
          existing.provenance.push(...association.provenance);
        } else {
          unlinked.push(association);
        }
        continue;
      }

      const componentId = implementation.system_component.id;
      let group = componentGroups.get(componentId);
      if (!group) {
        group = {
          id: componentId,
          title: implementation.system_component.title,
          controls: [],
        };
        componentGroups.set(componentId, group);
      }

      const existingControl = group.controls.find((item) =>
        item.control.reference.catalog_id === control.reference.catalog_id
        && item.control.reference.revision_id === control.reference.revision_id
        && item.control.reference.oscal_control_id === control.reference.oscal_control_id
      );
      if (existingControl) {
        existingControl.implementationIds.push(...association.implementationIds);
        existingControl.statuses.push(...association.statuses);
        existingControl.oscalStatuses.push(...association.oscalStatuses);
        existingControl.provenance.push(...association.provenance);
      } else {
        group.controls.push(association);
      }
    }
  }

  const groups = [...componentGroups.values()].sort((a, b) =>
    a.id.localeCompare(b.id)
  );

  return (
    <section aria-label={t("complianceExplorer.measuresTableLabel")}>
      <p className="panel muted" role="status">
        {t("complianceExplorer.currentPageMeasuresNotice", {
          shown: number(page.items.length),
          total: number(page.total),
        })}
      </p>

      {groups.map((group) => (
        <section className="panel" key={group.id} aria-label={
          group.title
            ? t("complianceExplorer.measureComponentTitle", { title: group.title })
            : t("complianceExplorer.measureComponentUnnamed")
        }>
          <h2>{group.title ?? t("complianceExplorer.measureComponentUnnamed")}</h2>
          <p className="muted mono">{t("complianceExplorer.componentId")}: {group.id}</p>
          <ul className="stack">
            {group.controls.map((association) => (
              <li key={controlKey(association.control)} className="panel">
                {renderControlAssociation(association, t, enumLabel)}
              </li>
            ))}
          </ul>
        </section>
      ))}

      {unlinked.length > 0 ? (
        <section className="panel" aria-label={t("complianceExplorer.unlinkedImplementations")}>
          <h2>{t("complianceExplorer.unlinkedImplementations")}</h2>
          <ul className="stack">
            {unlinked.map((association) => (
              <li key={controlKey(association.control)} className="panel">
                {renderControlAssociation(association, t, enumLabel)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {controlsWithoutImplementations.length > 0 ? (
        <section className="panel" aria-label={t("complianceExplorer.controlsWithoutImplementations")}>
          <h2>{t("complianceExplorer.controlsWithoutImplementations")}</h2>
          <ul className="stack">
            {controlsWithoutImplementations.map((control) => (
              <li key={controlKey(control)}>
                <strong>{control.reference.oscal_control_id}</strong> - {control.title}
                <div className="muted mono">
                  {t("complianceExplorer.source")}: {control.reference.catalog_id} / {control.reference.revision_id}
                </div>
                <div className="muted">
                  {t("complianceExplorer.memberships")}: {control.memberships.map((membership) => membership.profile_title).join(", ")}
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {groups.length === 0 && unlinked.length === 0 && controlsWithoutImplementations.length === 0 ? (
        <div className="empty">{t("complianceExplorer.emptyResult")}</div>
      ) : null}
    </section>
  );
}

function controlKey(control: ComplianceExplorerControlItem): string {
  return `${control.reference.catalog_id}:${control.reference.revision_id}:${control.reference.oscal_control_id}`;
}

function renderControlAssociation(
  association: MeasuresControlAssociation,
  t: Translate,
  enumLabel: (value: string) => string,
) {
  const { control } = association;
  return (
    <>
      <strong>{control.reference.oscal_control_id}</strong> - {control.title}
      <div className="muted mono">
        {t("complianceExplorer.source")}: {control.reference.catalog_id} / {control.reference.revision_id}
      </div>
      <div className="muted">
        {t("complianceExplorer.memberships")}: {control.memberships.map((membership) => membership.profile_title).join(", ")}
      </div>
      <dl className="meta-list">
        <dt>{t("complianceExplorer.implementationIds")}</dt>
        <dd className="mono">{association.implementationIds.join(", ")}</dd>
        <dt>{t("complianceExplorer.statuses")}</dt>
        <dd>
          {association.statuses.map((status, index) => (
            <span key={`${association.implementationIds[index]}-${status}`}>
              {index > 0 ? " · " : ""}
              {enumLabel(status)}
              {association.oscalStatuses[index]
                ? ` / ${enumLabel(association.oscalStatuses[index] as string)}`
                : ""}
            </span>
          ))}
        </dd>
        <dt>{t("complianceExplorer.provenance")}</dt>
        <dd className="mono">
          {association.provenance.map((item, index) => (
            <span key={`${item.profileId}-${item.importId}-${index}`}>
              {index > 0 ? " · " : ""}
              {item.profileId ?? t("complianceExplorer.na")}/{item.importId ?? t("complianceExplorer.na")}
            </span>
          ))}
        </dd>
      </dl>
    </>
  );
}

