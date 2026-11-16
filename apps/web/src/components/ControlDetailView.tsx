import { parameterText, renderProse } from "@/lib/safe";
import { useI18n } from "@/lib/i18n/provider";
import type { Translate } from "@/lib/i18n";
import { propertyLabel } from "@/lib/profile-browser";
import type { ControlDetail, Link, Part, Property, RelatedMapping } from "@/lib/types";

import { SafeLink } from "./SafeLink";

function Props({ items, labels }: { items: Property[]; labels: ReadonlyMap<string, string> }) {
  const { t } = useI18n();
  if (items.length === 0) return null;
  return (
    <table>
      <thead>
        <tr>
          <th scope="col">{t("controls.property")}</th>
          <th scope="col">{t("controls.value")}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => (
          <tr key={`${item.name}-${index}`}>
            <td>{item.name}</td>
            <td>
              <span className="prose">{renderProse(item.value, labels)}</span>
              {item.remarks ? <p className="prose">{renderProse(item.remarks, labels)}</p> : null}
              {item.ns ? <div className="muted mono">{t("controls.namespace")}: {item.ns}</div> : null}
              {item.class ? <div className="muted">{t("controls.class")}: {item.class}</div> : null}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Links({ items, labels }: { items: Link[]; labels: ReadonlyMap<string, string> }) {
  if (items.length === 0) return null;
  return (
    <ul>
      {items.map((item, index) => (
        <li key={`${item.href}-${index}`}>
          <SafeLink href={item.href}>{renderProse(item.text || item.href, labels)}</SafeLink>
          {item.rel ? <span className="muted"> ({item.rel})</span> : null}
        </li>
      ))}
    </ul>
  );
}

function PartView({ part, labels, readable = false }: { part: Part; labels: ReadonlyMap<string, string>; readable?: boolean }) {
  return (
    <div className="part">
      {!readable ? <div className="part-label">{part.name}</div> : null}
      {part.title ? <strong>{renderProse(part.title, labels)}</strong> : null}
      {part.props.map((prop, index) =>
        prop.name === "label" ? (
          <span key={index} className="mono">
            {renderProse(prop.value, labels)}{" "}
          </span>
        ) : null,
      )}
      {part.prose ? <p className="prose">{renderProse(part.prose, labels)}</p> : null}
      {!readable ? <Props items={part.props.filter((prop) => prop.name !== "label")} labels={labels} /> : null}
      <Links items={part.links} labels={labels} />
      {part.parts.map((child, index) => (
        <PartView key={child.id ?? index} part={child} labels={labels} readable={readable} />
      ))}
    </div>
  );
}

function References({ control, labels, anchorIds = true }: { control: ControlDetail; labels: ReadonlyMap<string, string>; anchorIds?: boolean }) {
  const { t } = useI18n();
  if (control.links.length === 0 && control.references.length === 0) return null;
  return <section aria-label={t("controls.references")}>
    <h2>{t("controls.references")}</h2>
    <Links items={control.links} labels={labels} />
    <ul>{control.references.map((reference) => <li key={reference.uuid} id={anchorIds ? reference.uuid : undefined}>
      <strong>{renderProse(reference.title ?? t("controls.untitledReference"), labels)}</strong>
      {reference.citation ? <span> — {renderProse(reference.citation, labels)}</span> : null}
      {reference.description ? <p className="prose">{renderProse(reference.description, labels)}</p> : null}
      {reference.rlinks.map((rlink, index) => <div key={index}><SafeLink href={rlink.href}>{rlink.href}</SafeLink></div>)}
    </li>)}</ul>
  </section>;
}

export function ControlDetailView({
  control, presentation = "catalog", relatedMappings, tenantId, relatedError, relatedLoading,
}: {
  control: ControlDetail;
  presentation?: "catalog" | "profile" | "technical";
  relatedMappings?: RelatedMapping[];
  tenantId?: string;
  relatedError?: string | null;
  relatedLoading?: boolean;
}) {
  const { t, number, enumLabel } = useI18n();
  const labels = parameterText(control.parameters);
  const { source_catalog: catalog, source_revision: revision } = control;
  const location = control.ancestors.map((ancestor) => ancestor.oscal_id ?? ancestor.title);

  if (presentation === "profile") {
    const properties = [...control.properties, ...control.parameters.flatMap((parameter) => parameter.props)];
    function collectProperties(parts: Part[]) {
      for (const part of parts) {
        properties.push(...part.props);
        collectProperties(part.parts);
      }
    }
    collectProperties(control.parts);
    const statements = control.parts.filter((part) => part.name === "statement");
    const guidance = control.parts.filter((part) => part.name !== "statement");
    return <article className="panel control-detail readable-detail" aria-label={`${control.oscal_control_id} ${control.title}`}>
      <h2><span className="mono">{control.oscal_control_id}</span> {renderProse(control.title, labels)}</h2>
      {statements.length > 0 ? <section aria-label={t("controls.requirementStatement")}>
        <h3>{t("controls.requirementStatement")}</h3>
        {statements.map((part, index) => <PartView key={index} part={part} labels={labels} readable />)}
      </section> : null}
      <dl className="meta-list">
        {["modal_verb", "sec_level", "target_object_categories"].map((name) => {
          const values = [...new Set(properties.filter((prop) => prop.name === name).map((prop) => prop.value))];
          return values.length ? <div className="requirement-fact" key={name}><dt>{propertyLabel(name, t)}</dt><dd>{renderProse(values.join(", "), labels)}</dd></div> : null;
        })}
      </dl>
      {guidance.length > 0 ? <section aria-label={t("controls.guidanceAdditionalInfo")}>
        <h3>{t("controls.guidanceAdditionalInfo")}</h3>
        {guidance.map((part, index) => <PartView key={index} part={part} labels={labels} readable />)}
      </section> : null}
      {control.parameters.length > 0 ? <section aria-label={t("controls.requirementParameters")}>
        <h3>{t("controls.requirementParameters")}</h3>
        <p className="muted">{t("controls.assignedValuesInfo")}</p>
        {control.parameters.map((parameter) => <div key={parameter.id}>
          <strong>{renderProse(parameter.label ?? parameter.id, labels)}</strong>
          {parameter.values.length > 0 ? <p className="prose">{renderProse(parameter.values.join(", "), labels)}</p> : null}
          {parameter.select ? <p className="prose">{parameter.select.how_many ? `${enumLabel(parameter.select.how_many)}: ` : ""}{renderProse(parameter.select.choices.join(" | "), labels)}</p> : null}
          {parameter.usage ? <p className="prose">{renderProse(parameter.usage, labels)}</p> : null}
          {parameter.guidelines.map((text, index) => <p key={index} className="prose">{renderProse(text, labels)}</p>)}
        </div>)}
      </section> : null}
      <References control={control} labels={labels} />
      <details className="technical-details">
        <summary>{t("controls.technicalOscalDetails")}</summary>
        <ControlDetailView control={control} presentation="technical" />
      </details>
    </article>;
  }

  return (
    <article className="panel control-detail" aria-labelledby="control-title">
      <h1 id="control-title">
        <span className="mono">{control.oscal_control_id}</span>
        <span>{renderProse(control.title, labels)}</span>
      </h1>
      <p className="source-banner">
        {t("controls.source")}: <strong>{catalog.name}</strong> · {t("controls.revisionLower", { name: number(revision.revision_number) })}{" "}
        <span className={revision.lifecycle_status === "published" ? "badge" : "badge badge-warn"}>
          {enumLabel(revision.lifecycle_status)}
        </span>{" "}
        · OSCAL {revision.oscal_version}
        {catalog.origin_type === "imported" ? ` · ${t("controls.imported")}` : ` · ${t("controls.internallyAuthored")}`}
      </p>
      {location.length > 0 ? (
        <p className="muted">
          {t("controls.location")}: {location.join(" › ")} › <span className="mono">{control.oscal_control_id}</span>
        </p>
      ) : null}
      {control.parts.length > 0 ? (
        <section aria-labelledby="control-content">
          <h2 id="control-content">{t("controls.content")}</h2>
          {control.parts.map((part, index) => (
            <PartView key={part.id ?? index} part={part} labels={labels} />
          ))}
        </section>
      ) : null}

      {control.parameters.length > 0 ? (
        <section aria-labelledby="control-params">
          <h2 id="control-params">{t("controls.parameters")}</h2>
          <table>
            <thead>
              <tr>
                <th scope="col">{t("controls.id")}</th>
                <th scope="col">{t("controls.label")}</th>
                <th scope="col">{t("controls.valueChoices")}</th>
              </tr>
            </thead>
            <tbody>
              {control.parameters.map((parameter) => (
                <tr key={parameter.id}>
                  <td className="mono">{parameter.id}</td>
                  <td>{renderProse(parameter.label ?? "—", labels)}</td>
                  <td>
                    {parameter.values.length > 0
                      ? renderProse(parameter.values.join(", "), labels)
                      : parameter.select
                        ? `${parameter.select.how_many ? enumLabel(parameter.select.how_many) : t("controls.choose")}: ${renderProse(parameter.select.choices.join(" | "), labels)}`
                        : renderProse(parameter.usage ?? "—", labels)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {control.parameters.map((parameter) => (
            <details key={parameter.id}>
              <summary>{t("controls.parameterDetails", { name: parameter.id })}</summary>
              {parameter.usage ? <p className="prose">{renderProse(parameter.usage, labels)}</p> : null}
              {parameter.depends_on ? <p>{t("controls.dependsOn")}: {parameter.depends_on}</p> : null}
              <Props items={parameter.props} labels={labels} />
              {parameter.constraints.map((constraint, index) => <div key={index}>
                {constraint.description ? <p className="prose">{renderProse(constraint.description, labels)}</p> : null}
                {constraint.tests.map((test, i) => <p className="prose" key={i}>{test.expression}{test.remarks ? ` — ${test.remarks}` : ""}</p>)}
              </div>)}
              {parameter.guidelines.map((guideline, index) => <p className="prose" key={index}>{renderProse(guideline, labels)}</p>)}
              <Links items={parameter.links} labels={labels} />
            </details>
          ))}
          <p className="muted">{t("controls.assignedValuesShown")}</p>
        </section>
      ) : null}

      {control.properties.length > 0 ? (
        <section aria-labelledby="control-props">
          <h2 id="control-props">{t("controls.properties")}</h2>
          <Props items={control.properties} labels={labels} />
        </section>
      ) : null}

      <References control={control} labels={labels} anchorIds={presentation !== "technical"} />
      {presentation === "catalog" && tenantId ? <RelatedMappingsSection
        mappings={relatedMappings ?? []} tenantId={tenantId} error={relatedError ?? null}
        loading={relatedLoading ?? false} /> : null}

      <section aria-labelledby="control-source">
        <h2 id="control-source">{t("controls.sourceIdentity")}</h2>
        <dl className="meta-list">
          <dt>{t("controls.catalog")}</dt>
          <dd>
            {catalog.name}
            {catalog.source_organization ? ` (${catalog.source_organization})` : ""}
          </dd>
          <dt>{t("controls.catalogId")}</dt>
          <dd className="mono">{control.reference.catalog_id}</dd>
          <dt>{t("controls.revisionId")}</dt>
          <dd className="mono">{control.reference.revision_id}</dd>
          <dt>{t("controls.controlId")}</dt>
          <dd className="mono">{control.reference.oscal_control_id}</dd>
          <dt>{t("controls.oscalDocument")}</dt>
          <dd className="mono">{control.oscal_document_uuid}</dd>
          {catalog.license_identifier ? (
            <>
              <dt>{t("controls.license")}</dt>
              <dd>{catalog.license_identifier}</dd>
            </>
          ) : null}
        </dl>
        <p className="muted">
          {t("controls.licenseNotice")}
        </p>
      </section>
      {control.raw_control ? <details>
        <summary>{t("controls.advancedTechnicalView")}</summary>
        <pre className="raw-oscal">{JSON.stringify(control.raw_control, null, 2)}</pre>
      </details> : null}
    </article>
  );
}

function RelatedMappingsSection({
  mappings, tenantId, error,
  loading,
}: {
  mappings: RelatedMapping[];
  tenantId: string;
  error: string | null;
  loading: boolean;
}) {
  const { t, number, enumLabel } = useI18n();
  return <section aria-labelledby="related-controls-title">
    <h2 id="related-controls-title">{t("controls.relatedRequirements")}</h2>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    {!error && loading ? <p role="status">{t("controls.loadingRelatedMappings")}</p> : null}
    {!error && !loading && mappings.length === 0 ? <p className="muted">{t("controls.noMappings")}</p> : null}
    {mappings.map((mapping) => {
      const selectedSet = mapping.matched_side === "source" ? mapping.sources : mapping.targets;
      const relatedSet = mapping.matched_side === "source" ? mapping.targets : mapping.sources;
      return <article className="related-mapping" key={`${mapping.collection_id}:${mapping.entry_uuid}`}>
        <h3>{mapping.relationship}</h3>
        <p>
          {t("controls.viewedFrom", {
            side: t(mapping.matched_side === "source" ? "controls.sourceSide" : "controls.targetSide"),
            selected: mappingSetLabel(selectedSet.length, t, number),
            related: mappingSetLabel(relatedSet.length, t, number),
          })}
        </p>
        {selectedSet.length > 1 || relatedSet.length > 1
          ? <p className="muted">{t("controls.relationshipBetweenSets")}</p> : null}
        <dl className="meta-list">
          <dt>{t("controls.matchingRationale")}</dt><dd>{mapping.matching_rationale}</dd>
          <dt>{t("controls.mappingCollection")}</dt>
          <dd><a href={`/t/${tenantId}/mappings/${mapping.collection_id}`}>{mapping.collection_title}</a></dd>
        </dl>
        <h4>{t("controls.relatedSet")}</h4>
        <ul>{relatedSet.map((related) => <li key={`${related.catalog_id}:${related.revision_id}:${related.control_id}`}>
          <a href={`/t/${tenantId}/catalogs/${related.catalog_id}?${new URLSearchParams({ revision: related.revision_id, control: related.control_id })}`}>
            {related.catalog_name} · {t("controls.revisionLower", { name: number(related.revision_number) })} · <span className="mono">{related.control_id}</span> — {related.title}
          </a>
        </li>)}</ul>
      </article>;
    })}
  </section>;
}

function mappingSetLabel(count: number, t: Translate, number: (value: number) => string): string {
  return count === 1 ? t("controls.oneRequirement") : t("controls.requirementSet", { name: number(count) });
}
