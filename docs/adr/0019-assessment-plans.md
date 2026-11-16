# 0019: OSCAL Assessment Plans

- Status: Accepted
- Date: 2026-11-16

## Context

Collaborative OSCAL needs tenant-owned Assessment Plans that remain bound to a specific
historical SSP implementation context while preserving the existing Trestle-first
OSCAL authoring architecture.

## Decision

- Introduce tenant-scoped `assessment_plans` working records and immutable
  `assessment_plan_versions` snapshots.
- Pin each Assessment Plan to one immutable `system_security_plan_version_id` at
  creation. This reference is immutable for the plan lifecycle.
- Store editable plan content as authoritative JSONB (`working_data`) with minimal
  relational projections for identity, tenant scope, system, pinned SSP version,
  title/description, and lifecycle timestamps.
- Author Assessment Plan OSCAL documents using Compliance Trestle 5.2.0
  (`trestle.oscal.assessment_plan`) at OSCAL 1.2.1.
- Bundle the official OSCAL 1.2.1 Assessment Plan schema
  (`oscal_assessment_plan_schema_v1.2.1.json`) from the NIST OSCAL v1.2.1 release
  artifact and verify SHA-256 (`0153e4e0414903c51c13732d4158d955630e33a3ef009d2691cf3e07336136f4`).
- Keep the three validation layers:
  1. Trestle model validation/serialization.
  2. Official version-specific JSON Schema validation.
  3. Application integrity checks (tenant, pinned SSP reference, baseline controls,
     objective/subject/activity/task/role-party reference integrity).
- Reuse immutable version semantics with substantive-content deduplication by digest,
  excluding volatile metadata fields (`uuid`, `metadata.last-modified`, `metadata.version`).
- Keep activities plan-local in the initial implementation; no reusable
  cross-plan procedure library.

## Consequences

- Assessment Plans preserve historical context and are insulated from mutable
  System/SSP working-state changes.
- Historical exports are served directly from stored immutable snapshots.
- Pinned SSP references and immutable version tables are protected by database-level
  constraints/triggers.
- Frontend adds an Assessment Plan workspace with overview, scope, activities,
  tasks, and validation/version interactions, including English and German labels.

## Deferred

- Reusable assessment procedure library.
- Assessment Results, observations, findings, POA&M, automated execution.
- Cross-plan execution/result sharing.

