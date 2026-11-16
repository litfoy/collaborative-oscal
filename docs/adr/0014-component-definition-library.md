# ADR 0014: Reusable OSCAL Component Definition library

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Organizations need reusable security and privacy measures that can explicitly
address requirements from multiple immutable Catalog revisions. These reusable
descriptions are distinct from the existing operational Control Implementation
Register and from future assessment conclusions.

## Decision

- Store tenant-owned Component Definition JSON as the authoritative document.
  Default compatible authoring to OSCAL 1.2.1 using Compliance Trestle 5.2.0's
  generated model, then validate the serialized document against the official
  NIST 1.2.1 JSON Schema and retain application integrity checks. Use OSCAL 1.2.3
  for the recognized 1.2.3-only component types `network`, `region`, `zone`,
  and `resource-container`. Preserve an existing document's declared version on
  ordinary edits. Imported or immutable source content is never rewritten by
  this authoring path.
- Keep multiple OSCAL components per document. Relational rows maintain stable
  internal document/component identities and project each implemented
  requirement's exact tenant Catalog, revision, and OSCAL control ID. They do
  not duplicate measure content. JSON and relational projections are committed
  together.
- Use one OSCAL control-implementation set per selected Catalog revision and
  retain exact control IDs and user-authored requirement descriptions. Validate
  each reference within the tenant, enforce it with composite foreign keys, and
  protect referenced revisions using a database trigger. Profiles are not
  normative sources in this POC.
- Retain internal component identity and OSCAL component UUID across edits.
  Preserve set and implemented-requirement UUIDs when their source revision and
  control subjects remain unchanged. A content edit creates a new OSCAL
  document UUID and updates `metadata.last-modified`; reads and exports do not.
- The POC stores only the current document. Users may deliberately delete
  components or documents; deletion removes only their identity and source
  projections. It does not remove Catalogs, revisions, or operational
  implementation records. Referenced revisions are protected while any
  application reference remains. Immutable Component Definition history,
  retirement, audit logs, and reference-aware deletion restrictions are future
  work for SSP and assessment integration.
- Reuse tenant `catalog:read` and `catalog:write` permissions and the existing
  BFF. Control Mappings are advisory discovery only; users explicitly select
  every requirement and author its implementation description.
- Do not associate these reusable components with existing operational
  implementations yet. Revisit explicit system-scoped component associations
  alongside OSCAL SSP support. Keep operational status, scope, responsibilities,
  evidence, and descriptions exclusively on the existing implementation
  records.

## Consequences and limitations

A Component Definition provides reusable implementation guidance, not evidence
that a measure is deployed or a control is satisfied. Exports refer to
tenant-authenticated revision URLs and are therefore not standalone portable.
Full import, Profile sources, capabilities, document history, SSPs, and
assessments are not implemented.
