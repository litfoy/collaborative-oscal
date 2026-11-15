# ADR 0017: Tenant-scoped Systems and immutable OSCAL SSP versions

## Status

Accepted

## Context

The application has revision-pinned normative catalogs and a requirement-specific
Implementation Register, but no stable identity for the actual system being
secured. An OSCAL System Security Plan (SSP) must represent system characteristics,
concrete components, and selected requirement contributions without replacing
those existing sources of truth. General Profile Resolution remains deferred
(ADR 0016), so this POC cannot safely treat a Profile as a resolved baseline.

## Decision

- Add a tenant-owned System with an optional existing Organization association.
  Its identity is independent of catalogs, baselines, and generated OSCAL document
  UUIDs. A System can have multiple SSPs.
- Each SSP pins one authorized Catalog revision. Baseline controls remain complete
  and immutable; a partial set of documented implementations is not a reduced
  baseline. Profile-backed SSPs and Profile Resolution are out of scope.
- Extend the existing Control Implementation record with optional System,
  concrete-component, and OSCAL implementation-status context. Legacy records
  remain unassigned until an explicit user action. A separate SSP membership
  relation records which contributions are included in each SSP and constrains
  tenant, System, component, control, and exact baseline identity.
- Store shared concrete component operational data on System components. Adopting
  a reusable Component Definition creates a distinct concrete component and an
  immutable, digest-addressed snapshot of the complete source document. The
  generated `imported-from` link points to an authenticated endpoint serving that
  historical source snapshot.
- Generate an OSCAL 1.2.3 SSP only from a consistent view of the System, SSP,
  concrete components, explicit memberships, and Implementation Register records.
  Store generated JSON as an immutable version. A normalized substantive-content
  digest avoids duplicate versions when the working state is unchanged.
- Validate the generated document with the bundled official NIST OSCAL 1.2.3 SSP
  JSON Schema and application-level baseline and internal-reference checks.
  Schema success is not a claim of exhaustive OSCAL Metaschema conformance,
  regulatory compliance, or assessment results.
- Keep operational workflow status separate from OSCAL implementation status.
  Require an explicitly authored OSCAL state for included contributions; require
  an explanation for planned, alternative, and not-applicable states. Do not infer
  status from components, mappings, evidence, or workflow status.
- Export only responsibilities and evidence that can be represented safely.
  Until application identities can be mapped to valid OSCAL parties and roles,
  retain responsibilities in the Implementation Register and include omission
  diagnostics. Only absolute HTTP(S) evidence references are serialized as links;
  references are not fetched or verified.
- Do not infer system identifiers, information types, classification, impact,
  operational status, authorization decisions, implementation claims, or parties.
  Drafts can be incomplete, but invalid drafts cannot become immutable versions.

## Consequences

Systems, concrete components, implementation contributions, and SSP versions have
separate identities and lifecycle boundaries. Updating operational data does not
alter historical versions. New baselines use new SSP records, and historical
versions remain pinned to their original Catalog revisions.

Compliance Trestle remains an architectural dependency. Its locked 5.2.0 SSP model
declares OSCAL 1.2.1, so it is not used or described as native 1.2.3 SSP support.
The SSP 1.2.3 model uses the existing JSON Schema compatibility path.

The initial UI is a Systems workspace for characteristics, components, explicit
contribution membership, validation diagnostics, and immutable version export.
It does not provide assessment conclusions or compliance scores.
