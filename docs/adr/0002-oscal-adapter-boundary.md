# ADR 0002: Isolate OSCAL and Trestle behind an adapter boundary

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

OSCAL documents are interoperability artifacts whose structure and versions may evolve. IBM compliance-trestle is a useful open-source integration candidate, but it must not dictate domain modeling or become a required hosted dependency.

## Decision

Place OSCAL parsing, validation, canonical JSON representation, import/export, and any Trestle calls behind `packages/oscal`. Keep domain/application models independent of OSCAL serialization structures. Use Trestle as an isolated adapter, not as the domain model.

## Consequences

The domain can evolve independently of OSCAL schemas and Trestle releases. The
package uses compliance-trestle 5.2.x generated models to validate selected Catalog
and Profile versions, but does not serialize source documents through them. Version-specific
support and bundled-schema selection are defined in
[ADR 0012](0012-oscal-versioned-schemas.md). The adapter does not expose Trestle
types outside `packages/oscal`; JSON Schema validation does not claim exhaustive
NIST Metaschema semantic coverage. Compatibility details and limitations are
maintained in the [Catalog import guide](../catalog-import.md).
