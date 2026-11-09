import { renderProse } from "@/lib/safe";
import type { ControlDetail, Link, Part, Property } from "@/lib/types";

import { SafeLink } from "./SafeLink";

function Props({ items }: { items: Property[] }) {
  if (items.length === 0) return null;
  return (
    <table>
      <thead>
        <tr>
          <th scope="col">Property</th>
          <th scope="col">Value</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => (
          <tr key={`${item.name}-${index}`}>
            <td>{item.name}</td>
            <td>{item.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Links({ items }: { items: Link[] }) {
  if (items.length === 0) return null;
  return (
    <ul>
      {items.map((item, index) => (
        <li key={`${item.href}-${index}`}>
          <SafeLink href={item.href}>{item.text || item.href}</SafeLink>
          {item.rel ? <span className="muted"> ({item.rel})</span> : null}
        </li>
      ))}
    </ul>
  );
}

function PartView({ part, labels }: { part: Part; labels: Record<string, string | undefined> }) {
  return (
    <div className="part">
      <div className="part-label">{part.name}</div>
      {part.title ? <strong>{part.title}</strong> : null}
      {part.props.map((prop, index) =>
        prop.name === "label" ? (
          <span key={index} className="mono">
            {prop.value}{" "}
          </span>
        ) : null,
      )}
      {part.prose ? <p className="prose">{renderProse(part.prose, labels)}</p> : null}
      <Links items={part.links} />
      {part.parts.map((child, index) => (
        <PartView key={child.id ?? index} part={child} labels={labels} />
      ))}
    </div>
  );
}

export function ControlDetailView({ control }: { control: ControlDetail }) {
  const labels: Record<string, string | undefined> = {};
  for (const parameter of control.parameters) {
    labels[parameter.id] = parameter.label ?? undefined;
  }
  const { source_catalog: catalog, source_revision: revision } = control;
  const location = control.ancestors.map((ancestor) => ancestor.oscal_id ?? ancestor.title);

  return (
    <article className="panel control-detail" aria-labelledby="control-title">
      <h1 id="control-title">
        <span className="mono">{control.oscal_control_id}</span>
        <span>{control.title}</span>
      </h1>
      <p className="source-banner">
        Source: <strong>{catalog.name}</strong> · revision {revision.revision_number}{" "}
        <span className={revision.lifecycle_status === "published" ? "badge" : "badge badge-warn"}>
          {revision.lifecycle_status}
        </span>{" "}
        · OSCAL {revision.oscal_version}
        {catalog.origin_type === "imported" ? " · imported" : " · internally authored"}
      </p>
      {location.length > 0 ? (
        <p className="muted">
          Location: {location.join(" › ")} › <span className="mono">{control.oscal_control_id}</span>
        </p>
      ) : null}
      <p>
        <span className="planned" aria-label="Add to Profile is planned for a later release">
          Add to Profile — coming later
        </span>
      </p>

      {control.parts.length > 0 ? (
        <section aria-labelledby="control-content">
          <h2 id="control-content">Control content</h2>
          {control.parts.map((part, index) => (
            <PartView key={part.id ?? index} part={part} labels={labels} />
          ))}
        </section>
      ) : null}

      {control.parameters.length > 0 ? (
        <section aria-labelledby="control-params">
          <h2 id="control-params">Parameters</h2>
          <table>
            <thead>
              <tr>
                <th scope="col">ID</th>
                <th scope="col">Label</th>
                <th scope="col">Value / choices</th>
              </tr>
            </thead>
            <tbody>
              {control.parameters.map((parameter) => (
                <tr key={parameter.id}>
                  <td className="mono">{parameter.id}</td>
                  <td>{parameter.label ?? "—"}</td>
                  <td>
                    {parameter.values.length > 0
                      ? parameter.values.join(", ")
                      : parameter.select
                        ? `${parameter.select.how_many ?? "choose"}: ${parameter.select.choices.join(" | ")}`
                        : (parameter.usage ?? "—")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {control.properties.length > 0 ? (
        <section aria-labelledby="control-props">
          <h2 id="control-props">Properties</h2>
          <Props items={control.properties} />
        </section>
      ) : null}

      {control.links.length > 0 || control.references.length > 0 ? (
        <section aria-labelledby="control-refs">
          <h2 id="control-refs">References</h2>
          <Links items={control.links} />
          <ul>
            {control.references.map((reference) => (
              <li key={reference.uuid}>
                <strong>{reference.title ?? "Untitled reference"}</strong>
                {reference.citation ? <span> — {reference.citation}</span> : null}
                {reference.description ? <p className="prose">{reference.description}</p> : null}
                {reference.rlinks.map((rlink, index) => (
                  <div key={index}>
                    <SafeLink href={rlink.href}>{rlink.href}</SafeLink>
                  </div>
                ))}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="control-source">
        <h2 id="control-source">Source identity</h2>
        <dl className="meta-list">
          <dt>Catalog</dt>
          <dd>
            {catalog.name}
            {catalog.source_organization ? ` (${catalog.source_organization})` : ""}
          </dd>
          <dt>Catalog ID</dt>
          <dd className="mono">{control.reference.catalog_id}</dd>
          <dt>Revision ID</dt>
          <dd className="mono">{control.reference.revision_id}</dd>
          <dt>Control ID</dt>
          <dd className="mono">{control.reference.oscal_control_id}</dd>
          <dt>OSCAL document</dt>
          <dd className="mono">{control.oscal_document_uuid}</dd>
          {catalog.license_identifier ? (
            <>
              <dt>License</dt>
              <dd>{catalog.license_identifier}</dd>
            </>
          ) : null}
        </dl>
        <p className="muted">
          Source catalogs may carry their own licence terms; availability here does not imply public
          redistribution rights.
        </p>
      </section>
    </article>
  );
}
