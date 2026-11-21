# ADR 0024: Compliance Explorer Read-Only Cross-Aggregate Projection

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

Collaborative OSCAL reuses shared governance information while preserving independent requirements, implementations, and assessments.

Users need to explore requirements selected from multiple Profiles in the context of one Information System, without introducing a second authoritative governance model.

Current CE-1, CE-2, and CE-3 implementation paths provide a tenant-scoped Compliance Explorer projection through a read-only endpoint and UI views, including server pagination and a page-local Measures grouping.

## Decision

- The Compliance Explorer is a tenant-scoped, read-only projection across existing aggregates; it is not an authoritative source separate from Profile, System, Control Implementation, and catalog-revision data.
- Users explicitly select exactly one Information System and one to five Profiles for exploration. This selection defines a request scope only and does not persist a System-to-Profile applicability assignment.
- Source Controls are identified by full source identity tuple: `(catalog_id, revision_id, oscal_control_id)`.
- Controls selected by multiple Profiles are deduplicated by full source identity while preserving all explicit Profile/import memberships.
- Only Control Implementations explicitly linked to the selected Information System are included as documented system implementations; original implementation status and Profile/import provenance are preserved.
- Measures grouping uses explicit System Component identity (`system_component_id`) and associated component record identity, never Component Definition identity or display-title matching.
- Requirements and Measures are alternative presentations of the same CE-1 projection, not separate authoritative models.
- CE-1 paginates Controls. The C-light Measures view groups only Controls on the currently loaded page and must explicitly disclose that unloaded pages are excluded.
- The projection must not modify source aggregates, published snapshots, or historical references.

## Semantic boundaries

- Profile selection in the Explorer does not imply normative applicability.
- An existing implementation record does not prove control effectiveness or compliance.
- Shared System Components do not imply equivalent requirements.
- Cross-catalog Mappings do not imply equivalent controls and do not automatically create implementations.
- Assessment Results remain independent from Explorer aggregation.
- The Explorer provides no inferred compliance score and no combined assessment conclusion.
- General OSCAL Profile Resolution remains deferred under ADR 0016.

## Consequences

### Benefits

- Reuses established OSCAL-native data and existing aggregate identities.
- Makes cross-domain governance relationships visible without flattening source semantics.
- Avoids duplicate persistence and synchronization logic.
- Preserves source identity, lineage, and traceability back to originating aggregates.

### Limitations

- No persistent System/Profile applicability relationship is created by Explorer usage.
- No complete global Measures aggregation exists across unloaded Control pages.
- No Mapping aggregation or Assessment Result aggregation is provided in the initial Explorer scope.
- No inferred legal applicability, implementation effectiveness, or compliance evaluation is produced.
- No authoring or mutation is supported through Explorer endpoints or views.

## References

- `docs/adr/0011-multiple-profile-catalog-imports.md`
- `docs/adr/0013-oscal-control-mappings.md`
- `docs/adr/0014-component-definition-library.md`
- `docs/adr/0016-defer-profile-resolution.md`
- `docs/adr/0017-system-security-plans.md`
- `docs/adr/0020-assessment-results.md`
- `docs/adr/0022-aggregate-optimistic-concurrency.md`

