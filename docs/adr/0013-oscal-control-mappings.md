# ADR 0013: OSCAL Control Mapping collections

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Normative controls from separate OSCAL Catalog revisions need explicit
relationship descriptions without changing or combining their authoritative
definitions. Mappings must preserve source and target direction and be
independent of Profiles, implementations, and assessment status.

## Decision

- Persist the official OSCAL `mapping-collection` document as authoritative
  JSONB. Keep a relational member projection only for tenant/revision/control
  referential integrity, revision protection, and related-control queries.
- Give each collection a stable tenant-scoped internal ID. Regenerate the OSCAL
  document UUID for document edits, retain mapping and map-entry UUIDs across
  edits when supplied, and increment the document version.
- Pin each mapping's source and target to exact catalog revisions. Validate
  original control identifiers against their own revision indexes. Same control
  IDs in different catalogs/revisions remain distinct identities.
- Update JSON and the relational lookup projection in one transaction. Composite
  foreign keys enforce tenant and revision scope; row locks and a database
  trigger protect referenced normative revisions from modification.
- Support set-to-set mappings, preserving many-to-many sets as one relationship.
  The first UI/API implementation selects whole controls. Statement-level
  members remain a future extension; no identifiers are synthesized.
- Support the official relationships and rationales. Invert only directional
  subset/superset relationships for reverse display. Do not infer transitivity,
  equality, or no-relationship from absent data.
- Generate OSCAL 1.2.3 collections. Dispatch Mapping validation through the
  existing OSCAL version registry: Compliance Trestle 5.2.0 for 1.2.0–1.2.1
  and official NIST schemas for 1.2.2–1.2.3. Do not generate OSCAL 1.1.3 Mapping
  documents; referenced Catalog versions are independent.
- Reuse tenant permission dependencies and the existing BFF. Export catalog
  resources through the existing authenticated revision API URL pattern.

## Consequences

Mapping semantics are not duplicated in relational columns, and mapping members
remain tied to the exact normative revision on which they were authored.
Collection deletion releases revision protection. Mapping document history is
not retained; only the current OSCAL document is stored.

Exports are not standalone portable because referenced catalog URLs require the
application API and authorization. Mapping import, statement-level UI,
confidence scoring, approval workflows, and automatic mapping are outside the
initial implementation.

See [OSCAL Control Mappings](../control-mappings.md) for supported versions,
relationship semantics, schema provenance, endpoints, and testing details.
