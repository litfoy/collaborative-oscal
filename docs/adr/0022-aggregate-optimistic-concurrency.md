# ADR 0022: Aggregate-Level Optimistic Concurrency Control

- **Status:** Accepted
- **Date:** 2026-11-18

## Context

Assessment Plan authoring introduced optimistic concurrency in ADR 0021 and validated it against real PostgreSQL contention, mapper version mismatches, API conflict translation, BFF forwarding, and frontend conflict UX. Assessment Results implemented and independently verified the same pattern for a second mutable aggregate.

The repository now needs one architectural standard for optimistic concurrency across mutable aggregates, without rewriting ADR 0021 or overstating current implementation coverage.

## Decision

- ADR 0021 remains unchanged as the original Assessment Plan decision record.
- This ADR establishes **aggregate-level optimistic concurrency** as the default architecture standard for mutable aggregates that expose working-state mutations.
- The standard requires:
  - a non-null numeric `concurrency_version` token,
  - SQLAlchemy mapper versioning (`version_id_col`) for stale-row detection,
  - explicit expected-version checks for applicable mutations of existing aggregates,
  - deterministic stale-update translation to HTTP `409` (`detail.code == "stale_update"`),
  - contract-level rejection of missing required tokens (`422`),
  - aggregate-level protection for nested mutations and publication flows,
  - immutable historical snapshots and tenant-safe isolation.
- Atomic publication semantics are part of the standard: a successful publish returns the updated concurrency token, stale publishes do not create extra snapshots, and idempotent publishes return existing snapshots without unnecessary token increments.
- The BFF and frontend contracts are part of the architecture boundary: conflict details must be preserved, unsaved edits must be preserved during conflicts, and destructive reload/discard actions require explicit confirmation.

## Scope and implementation coverage

- **Current verified reference implementations:**
  - Assessment Plans (`apps/api/app/application/assessment_plans.py` and related API/frontend tests)
  - Assessment Results (`apps/api/app/application/assessment_results.py` and related API/frontend tests)
- **Not yet implemented for other mutable aggregates:** coverage will be extended incrementally in Tasks 09c-09g.
- This ADR defines the standard now; implementation rollout remains explicit per aggregate.

## Consequences

- New mutable aggregate implementations must follow this standard and its verification contract instead of inventing per-aggregate concurrency semantics.
- Design and review discussions can distinguish:
  - architectural requirements (this ADR), and
  - concrete implementation and verification procedures (`docs/architecture/optimistic-concurrency.md`).
- Concurrency guarantees are now a cross-aggregate architecture concern, but implementation status remains aggregate-specific until verified.

