// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import type { Translate } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import type {
  ComplianceExplorerControlItem,
  ComplianceExplorerImplementation,
  ComplianceExplorerPage,
} from "@/lib/types";

interface MeasuresControlAssociation {
  control: ComplianceExplorerControlItem;
  implementations: ComplianceExplorerImplementation[];
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
        implementations: [implementation],
      };

      if (implementation.system_component_id === null || implementation.system_component === null) {
        const existing = unlinked.find((item) =>
          item.control.reference.catalog_id === control.reference.catalog_id
          && item.control.reference.revision_id === control.reference.revision_id
          && item.control.reference.oscal_control_id === control.reference.oscal_control_id
        );
        if (existing) {
          existing.implementations.push(...association.implementations);
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
        existingControl.implementations.push(...association.implementations);
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
      <p className="panel ce-page-scope-notice" role="status">
        {t("complianceExplorer.currentPageMeasuresNotice", {
          shown: number(page.items.length),
          total: number(page.total),
        })}
      </p>

      {groups.length > 0 ? (
        <section className="panel" aria-label={t("complianceExplorer.linkedComponents")}>
          <h2>{t("complianceExplorer.linkedComponents")}</h2>
          <p className="muted">
            {t("complianceExplorer.linkedComponentsCount", {
              count: number(groups.length),
            })}
          </p>

          {groups.map((group) => (
            <section className="panel ce-component-group" key={group.id} aria-label={
              group.title
                ? t("complianceExplorer.measureComponentTitle", { title: group.title })
                : t("complianceExplorer.measureComponentUnnamed")
            }>
              <h3>{group.title ?? t("complianceExplorer.measureComponentUnnamed")}</h3>
              <p className="muted mono">{t("complianceExplorer.componentId")}: {group.id}</p>
              <ul className="stack ce-control-associations">
                {group.controls.map((association) => (
                  <li key={controlKey(association.control)} className="panel ce-control-association">
                    {renderControlAssociation(association, t, enumLabel)}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </section>
      ) : null}

      {unlinked.length > 0 ? (
        <section className="panel" aria-label={t("complianceExplorer.unlinkedImplementations")}>
          <h2>{t("complianceExplorer.unlinkedImplementations")}</h2>
          <p className="muted">{t("complianceExplorer.unlinkedImplementationsHint")}</p>
          <ul className="stack ce-control-associations">
            {unlinked.map((association) => (
              <li key={controlKey(association.control)} className="panel ce-control-association">
                {renderControlAssociation(association, t, enumLabel)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {controlsWithoutImplementations.length > 0 ? (
        <section className="panel" aria-label={t("complianceExplorer.controlsWithoutImplementations")}>
          <h2>{t("complianceExplorer.controlsWithoutImplementations")}</h2>
          <p className="muted">{t("complianceExplorer.controlsWithoutImplementationsHint")}</p>
          <ul className="stack">
            {controlsWithoutImplementations.map((control) => (
              <li key={controlKey(control)} className="panel ce-undocumented-control">
                <p className="ce-control-heading">
                  <strong className="mono">{control.reference.oscal_control_id}</strong>
                  <span>{control.title}</span>
                </p>
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
      <p className="ce-control-heading">
        <strong className="mono">{control.reference.oscal_control_id}</strong>
        <span>{control.title}</span>
      </p>
      <div className="muted mono">
        {t("complianceExplorer.source")}: {control.reference.catalog_id} / {control.reference.revision_id}
      </div>
      <div className="muted">
        {t("complianceExplorer.memberships")}: {control.memberships.map((membership) => membership.profile_title).join(", ")}
      </div>
      <ul className="stack ce-implementation-list" aria-label={t("complianceExplorer.implementations")}>
        {association.implementations.map((implementation) => (
          <li className="panel ce-implementation-card" key={implementation.id}>
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
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
