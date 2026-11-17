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
- Database constraints/triggers protect pinned AP references and immutable
  versions; foreign-key `RESTRICT` semantics protect historical references from
  deletion.
- Users author domain-oriented structured fields without raw JSON authoring or
  manual UUID entry.

## Deferred

- Shared evidence library/management.
- C2P integration.
- Risk management workflows.
- POA&M authoring.

