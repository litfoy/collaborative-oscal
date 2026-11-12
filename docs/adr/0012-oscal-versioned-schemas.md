# ADR 0012: Explicit OSCAL versions and bundled schemas

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Catalog import and Profile generation previously supported OSCAL 1.1.3 and 1.2.1
through different validation paths. Trestle 5.2.0 generated models target OSCAL
1.2.1 and include backward-compatibility handling. OSCAL 1.2.2 and 1.2.3 introduce
schema-level differences, so these versions require their own official schemas.

## Decision

- Support Catalog and Profile documents for OSCAL 1.1.3, 1.2.0, 1.2.1, 1.2.2, and
  1.2.3. Keep this allowlist explicit. Use Trestle 5.2.0 models through OSCAL 1.2.1
  (including its backward-compatibility handling for earlier documents), and use
  the bundled official NIST JSON Schema selected by document model and
  `metadata.oscal-version` for 1.2.2 and 1.2.3.
- Default newly generated Profiles to OSCAL 1.2.3. Preserve the declared version
  of existing Profiles and imported Catalog revisions; do not infer a Profile
  version from its source Catalogs or rewrite existing documents.
- Bundle schema assets from the official [NIST OSCAL releases](https://github.com/usnistgov/OSCAL/releases)
  only for 1.2.2 and 1.2.3. Record resource hashes and fixture provenance in the
  [Catalog import guide](../catalog-import.md). Runtime validation does not download schemas.
- Treat the bundled 1.2.2 and 1.2.3 schemas as a compatibility bridge. Replace
  their validation paths with compliance-trestle models once an approved Trestle
  release supports those OSCAL versions, while retaining version-specific tests
  and preserving source documents.
- Use Trestle model validation for documents through OSCAL 1.2.1 and JSON Schema
  validation for 1.2.2 and 1.2.3. Never serialize a Trestle model back over an
  imported or persisted document. Catalog `x-` extension properties are preserved
  in the source document but excluded from the validation view; extension-specific
  constraints are not validated.
- Keep Catalog projection checks, including duplicate control-ID rejection,
  separate from document-model/schema validation. Validation does not imply complete
  NIST Metaschema semantic conformance or successful Profile resolution.
- Make no database migration. OSCAL versions are stored as unconstrained strings,
  and enabling a new version must not mutate Catalog JSONB, revision identities,
  Profile import identities, implementation records, or responsibilities.

## Consequences

OSCAL 1.2.2 NIST content and existing OSCAL 1.1.3 BSI content can be retained as
normative source revisions and referenced together by a newly generated 1.2.3
Profile. The Profile schema validates its declared model and version only; it does
not resolve source links or merge controls. Neither Trestle model validation nor
JSON Schema validation claims comprehensive OSCAL semantic validation.
