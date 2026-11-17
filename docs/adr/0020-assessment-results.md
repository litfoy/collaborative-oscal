# 0020: OSCAL Assessment Results

- Status: Accepted
- Date: 2026-11-17

## Context

Collaborative OSCAL needs tenant-owned Assessment Results records that remain bound
to one immutable Assessment Plan version and preserve revision-safe historical
references for subjects, statements, objectives, and exported OSCAL documents.

## Decision

- Introduce tenant-scoped `assessment_results` working records and immutable
  `assessment_result_versions` snapshots.
- Pin each Assessment Results record to one immutable
  `assessment_plan_version_id` at creation; this reference is immutable.
- Store editable result content as authoritative JSONB (`working_data`) with
  relational projections for tenant, system, pinned Assessment Plan version,
  title/description, and lifecycle timestamps.
- Keep three validation layers for version creation:
  1. Compliance Trestle model validation/serialization.
  2. Official OSCAL 1.2.1 Assessment Results JSON Schema validation.
  3. Application integrity checks for pinned historical scope and references.
- Enforce application-level integrity for:
  - planned-vs-actual reviewed-control scope (`historical baseline -> pinned AP scope -> actual AR scope`),
  - finding targets (`statement-id`/`objective-id`) resolved from pinned history,
  - observation subject UUIDs resolved from explicit pinned AP subject selections,
  - related-observation UUID referential integrity,
  - observation method policy (`EXAMINE|INTERVIEW|TEST`).
- Treat Assessment Plans without explicit `assessment-subjects` selections as authorizing no explicit component subject references in Assessment Results observations.
- Require every published manually-authored finding to reference at least one related observation UUID; incomplete drafts may be saved but cannot validate/publish.
- Keep backend enforcement authoritative; frontend filtering and guardrails do not relax service-layer checks.
- Require explicit user decisions before removing relationships that would reinterpret finding meaning (for example deleting referenced observations).
- Preserve explicitly supplied observation, finding, and evidence UUIDs. For nested entities without an explicit UUID, generate a new UUID; never infer identity from list position.
- Reject duplicate UUIDs within each authored entity namespace and reject evidence UUID collisions across the whole Assessment Results working document.
- Keep application-generated `relevant-evidence.href` fragment references (`#resource-uuid`) internal to OSCAL serialization while requiring manually-authored evidence resource URLs to be absolute HTTP(S) URLs.
- Reject manually-authored evidence URLs that are fragment-only, relative, scheme-relative, credentialed, malformed, or use unsupported/dangerous schemes.
- Generate immutable snapshots with substantive-content deduplication by digest,
  excluding volatile root metadata (`uuid`, `metadata.last-modified`,
  `metadata.version`).
- Add Assessment Results API, BFF allow-list paths, dedicated navigation, and
  structured UI editors for observations, evidence, and findings in English and
  German.

## Consequences

- Assessment Results preserve fixed historical context across AP/SSP/catalog
  evolution and can be exported directly from immutable snapshots.
- Existing immutable Assessment Results snapshots remain unchanged after integrity-policy hardening; no historical rewrite or regeneration is performed.
- Existing working drafts remain readable after integrity-policy hardening. Invalid drafts must be corrected by authors before validation/publication; the service does not silently regenerate UUIDs, relink findings, remove evidence, or rewrite evidence URLs.
- Database constraints/triggers protect pinned AP references and immutable
  versions; foreign-key `RESTRICT` semantics protect historical references from
  deletion.
- Users author domain-oriented structured fields without raw JSON authoring or
  manual UUID entry.

## Notes

- If a client explicitly reuses a previously deleted UUID for a replacement entity, that explicit UUID is preserved by design. The service does not maintain an external identity-registry history for deleted nested entities.

## Deferred

- Shared evidence library/management.
- C2P integration.
- Risk management workflows.
- POA&M authoring.

