# ADR 0021: Optimistic concurrency for Assessment Plans

- **Status:** Proposed
- **Date:** 2026-11-18

## Context

Assessment Plan working documents contain title, description, nested JSONB working data, and publication state. Concurrent edits could otherwise use last-writer-wins behavior and silently overwrite another editor's changes.

## Decision

- Assessment Plan records use SQLAlchemy mapper versioning with a non-null integer `concurrency_version`, initially `1`.
- Every Assessment Plan update and publication requires `expected_version`.
- Updates and publication compare the expected and persisted versions under existing tenant-scoped pessimistic locking.
- SQLAlchemy stale-row detection also guards ORM flushes and JSONB aggregate changes.
- Rejected mutations return HTTP `409` with `detail.code == "stale_update"`, the plan ID, and expected/current versions.
- The BFF preserves 409 and conflict details.
- The frontend preserves unsaved editor state and requires explicit confirmation before reload/discard.
- Immutable Assessment Plan versions remain append-only and retain their existing digest policy.

## Consequences

- Missing `expected_version` is rejected by the API contract.
- Concurrent transactions cannot silently publish or overwrite newer working state.
- A stale publication does not create a version or alter the aggregate plan version.
- This decision applies only to Assessment Plans. Other mutable entities are not rolled into this change.

