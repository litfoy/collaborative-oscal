# ADR 0012: Explicit OSCAL versions and model-based authoring

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Catalog import and Profile generation support multiple declared OSCAL versions
through different validation paths. Compliance Trestle 5.2.0 generated models
target OSCAL 1.2.1. Some older valid documents, such as a 1.0.0 Profile using
`merge.combine.method`, are rejected by those models. OSCAL 1.2.2 and 1.2.3
introduce schema-level differences, so these versions require their own official
schemas.

## Decision

- Support Catalog and Profile documents for OSCAL 1.0.0–1.0.6, 1.1.0–1.1.3,
  and 1.2.0–1.2.3. Keep this allowlist explicit. Use Trestle 5.2.0 models for
  1.1.3, 1.2.0, and 1.2.1, and use the bundled official NIST JSON Schema selected
  by document model and `metadata.oscal-version` for 1.0.0–1.0.6, 1.1.0–1.1.2,
  1.2.2, and 1.2.3.
- Use OSCAL 1.2.1 as the preferred target for newly authored compatible Profiles,
  Mapping collections, Component Definitions, and SSPs. Use the corresponding
  generated Trestle model for construction/serialization and independently
  validate the final JSON against the official version-specific NIST schema.
  Retain application integrity checks. Component Definitions and SSPs use 1.2.3
  when recognized required content cannot be represented in 1.2.1.
- Preserve the declared version of existing editable documents during ordinary
  edits. Do not infer Profile versions from source Catalogs, silently downgrade
  documents, or reserialize imported Catalogs, adoption snapshots, or immutable
  SSP versions. Existing compatibility adapters remain available.
- Bundle schema assets from the official [NIST OSCAL releases](https://github.com/usnistgov/OSCAL/releases).
  Record resource hashes and provenance in the [Catalog import guide](../catalog-import.md).
  Runtime validation does not download schemas.
- Treat the bundled 1.2.2 and 1.2.3 schemas as a compatibility bridge. Replace
  their validation paths with compliance-trestle models once an approved Trestle
  release supports those OSCAL versions, while retaining version-specific tests
  and preserving source documents.
- Use the established validation dispatch for imported documents: Trestle model
  validation for 1.1.3, 1.2.0, and 1.2.1 and JSON Schema validation for the other
  supported versions. Never serialize a Trestle model back over an imported or
  historical document. Catalog `x-` extension properties are preserved in the
  source document but excluded from the validation view; extension-specific
  constraints are not validated.
- Trestle parsing/model validation, official JSON Schema validation, application
  integrity checks, and successful cross-document resolution are distinct
  guarantees. Serialization must not silently coerce or omit explicit authored
  content.
- Keep Catalog projection checks, including duplicate control-ID rejection,
  separate from document-model/schema validation. Validation does not imply complete
  NIST Metaschema semantic conformance or successful Profile resolution.
- Make no database migration. OSCAL versions are stored as unconstrained strings,
  and enabling a new version must not mutate Catalog JSONB, revision identities,
  Profile import identities, implementation records, or responsibilities.

## Consequences

OSCAL 1.2.2 NIST content and existing OSCAL 1.1.3 BSI content can be retained as
normative source revisions and referenced together by a newly generated 1.2.1
Profile. The Profile model/schema checks do not resolve source links or merge
controls. Neither Trestle model validation nor JSON Schema validation claims
comprehensive OSCAL semantic validation. Future Assessment Plans, Assessment
Results, and POA&M implementations must use generated Trestle models from the
beginning wherever the target version supports the required semantics.
