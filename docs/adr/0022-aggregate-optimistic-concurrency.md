# ADR 0022: Aggregate-Level Optimistic Concurrency Control

- **Status:** Accepted
- **Date:** 2026-11-18

## Context

Assessment Plan authoring introduced optimistic concurrency in ADR 0021 and validated it against real PostgreSQL contention, mapper version mismatches, API conflict translation, BFF forwarding, and frontend conflict UX. Assessment Results implemented and verified the same pattern for a second mutable aggregate through maintainer-led, AI-assisted review.

The repository now needs one architectural standard for optimistic concurrency across mutable aggregates, without rewriting ADR 0021 or overstating current implementation coverage.

## Decision

- ADR 0021 remains unchanged as the original Assessment Plan decision record.
- This ADR establishes **aggregate-level optimistic concurrency** as the default architecture standard for mutable aggregates that expose working-state mutations.
- The standard requires:
  - a non-null integer `concurrency_version` token initialized to `1`,
  - SQLAlchemy mapper versioning (`version_id_col`) for stale-row detection,
  - explicit expected-version checks for all applicable mutations of existing aggregates (including deletion where supported),
  - deterministic stale-update translation to HTTP `409` (`detail.code == "stale_update"`),
  - contract-level rejection of missing required tokens (`422`),
  - aggregate-level protection for nested mutations and publication flows,
  - aggregate rules ensuring every effective protected-state mutation advances the aggregate version, including nested relational and bulk mutation paths not automatically covered by mapper versioning,
  - immutable historical snapshots and tenant-safe isolation.
- Atomic publication semantics are part of the standard: a successful publish returns the updated concurrency token, stale publishes do not create extra snapshots, and idempotent publishes return existing snapshots without unnecessary token increments.
- The BFF and frontend contracts are part of the architecture boundary: conflict details must be preserved, unsaved edits must be preserved during conflicts, all relevant editor inputs and mutation actions must be protected during pending save/publication/conflict-reload requests, and destructive reload/discard actions require explicit confirmation.
- Automatic conflict merging and silent overwrites are prohibited.

## Scope and implementation coverage

- **Implemented aggregates:**
  - Assessment Plans
  - Assessment Results
  - System Security Plans (SSPs)
  - Profiles
  - Mapping Collections
- **Implementation review and verification status:**
  - Assessment Plans, Assessment Results, and SSPs have established review and verified contention/reference coverage (reviewed by the maintainer with AI-assisted analysis; no external audit).
  - Profiles and Mapping Collections have implemented concurrency paths, but do not yet have the same review and verification status.
- Operation-specific requirements apply only where those operations exist for an aggregate (for example: publication, idempotent publication, immutable snapshots, deletion endpoints, or nested authored structures).
- This ADR defines the standard now; rollout remains explicit per aggregate.

## Consequences

- New mutable aggregate implementations must follow this standard and its verification contract instead of inventing per-aggregate concurrency semantics.
- Design and review discussions can distinguish:
  - architectural requirements (this ADR), and
  - concrete implementation and verification procedures (`docs/architecture/optimistic-concurrency.md`).
- Concurrency guarantees are now a cross-aggregate architecture concern, but implementation status remains aggregate-specific until verified.