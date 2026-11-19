# Optimistic Concurrency Implementation and Verification Guide

This guide defines the reusable implementation and verification contract for aggregate-level optimistic concurrency.

- Architectural decision: `docs/adr/0022-aggregate-optimistic-concurrency.md`
- Original Assessment Plan decision (kept unchanged): `docs/adr/0021-assessment-plan-optimistic-concurrency.md`
- Verified reference implementations: Assessment Plans and Assessment Results only

## Implementation Contract

The following behaviors are required for mutable aggregate implementations that adopt ADR 0022.

1. **Mapper-backed concurrency token**
   - Use SQLAlchemy mapper versioning with `version_id_col` bound to aggregate `concurrency_version`.
   - Keep `concurrency_version` as a non-null integer initialized to `1`.
   - Reference: `apps/api/app/persistence/models.py` (`AssessmentPlanRecord`, `AssessmentResultRecord`).
   - Migration pattern reference: `migrations/versions/e1f2a3b4c5d6_assessment_plan_concurrency.py`, `migrations/versions/f7a1c9e2d4b3_assessment_result_concurrency.py`.

2. **Required expected version for existing-aggregate mutations**
   - Require `expected_version` for all applicable mutations of existing aggregates.
   - Where supported by aggregate behavior, this includes update, publication, and deletion mutations.
   - Missing required token must fail contract validation (`422`).
   - Reference: `apps/api/app/api/assessment_plan_schemas.py`, `apps/api/app/api/assessment_result_schemas.py`.

3. **Explicit token comparison plus mapper stale detection**
   - Compare `expected_version` to persisted `concurrency_version` before mutation.
   - Also treat failed flush stale-row detection (`StaleDataError`) as stale update and translate consistently.
   - Reference: `apps/api/app/application/assessment_plans.py` (`update_plan`, `create_version`), `apps/api/app/application/assessment_results.py` (`update_result`, `create_version`).

4. **Aggregate-level protection, including nested-only mutations**
   - Protect the whole aggregate working state (including nested JSON/relational payloads), not only top-level scalar fields.
   - Every effective mutation of protected aggregate state must advance `concurrency_version`, including nested relational and bulk mutation paths not automatically covered by mapper versioning.
   - Preserve established no-op semantics: no-op operations do not need to increment the token.
   - Cover mutation paths where mapper versioning alone is not sufficient by adding explicit version checks and targeted regression tests.
   - Verified nested-only reference: `test_assessment_result_nested_only_update_advances_concurrency_version` in `apps/api/tests/test_assessment_results.py`.

5. **Structured stale conflict and input error contracts**
   - Return HTTP `409` with stable `detail.code == "stale_update"` and expected/current version details.
   - Return HTTP `422` when required version token is missing.
   - References:
     - Routes: `apps/api/app/api/assessment_plan_routes.py`, `apps/api/app/api/assessment_result_routes.py`
     - API tests: `apps/api/tests/test_assessment_plan_api_concurrency.py`, `apps/api/tests/test_assessment_result_api_concurrency.py`

6. **Atomic publication and token propagation**
   - Publication is atomic with aggregate version advancement where publication exists.
   - Publish responses must propagate the resulting token so subsequent client writes use the correct `expected_version`.
   - Idempotent publication (where supported) reuses the existing immutable snapshot and does not increment tokens unnecessarily.
   - References:
     - Service behavior: `apps/api/app/application/assessment_plans.py`, `apps/api/app/application/assessment_results.py`
     - Backend tests: `test_assessment_result_idempotent_publish_reuses_snapshot_without_token_increment` in `apps/api/tests/test_assessment_results.py`
      - API token propagation tests: `test_publish_then_save_uses_returned_token_without_false_conflict` in `apps/api/tests/test_assessment_plan_api_concurrency.py` and `apps/api/tests/test_assessment_result_api_concurrency.py`.
      - Frontend token propagation tests: `"synchronizes the publication token so a subsequent save does not conflict"` in `apps/web/tests/assessment-plan-workspace.test.tsx` and `apps/web/tests/assessment-result-workspace.test.tsx`.

7. **BFF and frontend conflict handling contract**
   - Preserve backend `409` payloads through the BFF unchanged.
   - Frontend must send `expected_version`, keep unsaved edits during conflicts, and prohibit automatic conflict merging or silent overwrite behavior.
   - During pending save, publication, and conflict-reload requests, all relevant editor inputs and mutation actions must be protected (disabled or otherwise blocked) until completion.
   - Discard/reload after conflict requires explicit user confirmation.
   - References:
     - BFF proxy: `apps/web/src/app/bff/[...path]/route.ts`
     - Frontend error classification: `apps/web/src/lib/bff-client.ts`
     - Workspaces: `apps/web/src/components/AssessmentPlanWorkspace.tsx`, `apps/web/src/components/AssessmentResultWorkspace.tsx`
     - Frontend regressions: `apps/web/tests/assessment-plan-workspace.test.tsx`, `apps/web/tests/assessment-result-workspace.test.tsx`

8. **Historical snapshot immutability and tenant isolation**
   - Where immutable versions exist, they remain append-only historical snapshots.
   - Where publication exists, stale publish attempts must not create extra snapshots.
   - Keep tenant scoping in lock/query paths and migrations (`tenant_id` filters and constraints).
   - References: application services and persistence models above.

## Transaction Handling Pattern

This section explains the required transaction pattern and why it is structured this way.

1. **Preserve existing pessimistic locks for mutation entry points**
   - Continue using tenant-scoped row locking for aggregate fetches in mutating paths (`with_for_update`).
   - References: `_get_plan(..., lock=True)` and `_get_result(..., lock=True)` call sites in update/publish methods.

2. **Use explicit token checks and mapper versioning as complementary controls**
   - Explicit checks reject stale clients early with deterministic conflict details.
   - Mapper versioning catches late stale-row cases during flush.
   - Either mechanism alone is incomplete:
     - explicit check alone can miss stale flush races,
     - mapper stale detection alone does not provide stable pre-mutation semantics for API clients.

3. **Translate `StaleDataError` outside failed session scope**
   - On flush mismatch, capture a marker exception in-transaction, exit failed session context, then read current version in a fresh valid transaction.
   - References:
     - `_StaleAssessmentPlanFlush` + `_current_plan_version` path in `apps/api/app/application/assessment_plans.py`
     - `_StaleAssessmentResultFlush` + `_current_result_version` path in `apps/api/app/application/assessment_results.py`

4. **Retrieve current version in a valid transaction**
   - Do not rely on in-session state after flush failure.
   - Re-read current version through a new scope to report correct conflict metadata.

5. **Connection-bound session compatibility (including savepoint-capable scopes)**
   - Service constructors accept injected session scopes, allowing connection-bound usage patterns.
   - Reference usage in deterministic overlap tests: `_bound_scope` helpers and threaded tests in `apps/api/tests/test_assessment_plans.py` and `apps/api/tests/test_assessment_results.py`.
   - Savepoint-capable session composition remains compatible because stale translation is performed after exiting failed scope.

6. **Acknowledge mapper-versioning limits for bulk and nested relational mutation paths**
   - Mapper versioning does not replace aggregate-level mutation discipline for bulk SQL paths or domain-specific nested mutation side effects.
   - Implement explicit mutation handling so each effective protected-state change still advances `concurrency_version` when mapper automation does not do so.
   - Keep explicit checks, lock discipline, and targeted regressions for those paths.

7. **Atomic rollback requirements**
   - Failed update/publish attempts must roll back as one unit.
   - No partial aggregate updates and no partial immutable snapshot creation on conflict.
   - References: stale publish tests that assert unchanged snapshot count/identity and unchanged aggregate version.

### Failure modes and why this pattern avoids them

- **Lost updates (last writer wins):** prevented by required `expected_version` checks and stale translation.
- **Silent stale flush overwrites:** prevented by mapper stale detection and `StaleDataError` translation.
- **Incorrect conflict metadata after transaction failure:** avoided by re-reading current version in a fresh scope.
- **Partial publication side effects:** avoided by transaction rollback and append-only snapshot assertions.
- **Client-side false conflicts after publish:** avoided by returning and reusing updated concurrency tokens.

## Concurrency Verification Contract

This section separates mandatory behavioral guarantees from persistence-specific test techniques.

### Mandatory behavioral guarantees

Every aggregate adopting ADR 0022 must prove:

1. stale mutation requests are rejected with stable `409 stale_update` details for supported mutating operations,
2. missing required expected-version tokens are rejected (`422`),
3. exactly one winner persists under concurrent overlap for conflicting writes,
4. effective protected-state mutations advance `concurrency_version` (with established no-op semantics preserved),
5. frontend preserves unsaved edits on conflict, blocks relevant mutation actions while pending, and requires explicit confirmation before discard/reload,
6. automatic conflict merge and silent overwrite behavior is not introduced.

### Operation-specific guarantees

Apply these guarantees only to aggregates that expose the corresponding operation or structure.

1. **Publication + immutable snapshots (where present)**
   - stale publish attempts do not create extra immutable snapshots,
   - idempotent publish reuse does not increment tokens unnecessarily,
   - publication responses propagate the current token for subsequent writes.

2. **Deletion (where supported)**
   - deletion requires `expected_version`,
   - stale deletion attempts return structured `409 stale_update` behavior.

3. **Nested authored structures (where present)**
   - nested-only effective mutations advance the aggregate token and participate in stale detection.

### Verified techniques used by Assessment Plans and Assessment Results

1. **Deterministic PostgreSQL overlap with real lock contention evidence**
   - Use threaded overlap and gated lock release.
   - Confirm real blocking via `pg_blocking_pids()` before releasing the lock.
   - References:
     - AP: `test_assessment_plan_update_rejects_stale_token_under_concurrent_transactions`, `test_assessment_plan_publish_rejects_stale_token_under_concurrent_transactions` in `apps/api/tests/test_assessment_plans.py`
     - AR: `test_assessment_result_update_rejects_stale_token_under_concurrent_transactions`, `test_assessment_result_publish_rejects_stale_token_under_concurrent_transactions`, `test_assessment_result_version_creation_is_stable_under_concurrency` in `apps/api/tests/test_assessment_results.py`

2. **Bounded synchronization and cleanup discipline**
   - Use bounded barriers/events/timeouts, then always release gates in `finally` blocks.
   - Prevents hanging tests and false positives from unresolved worker states.

3. **Real mapper mismatch regressions**
   - Force ORM version mismatch with SQL `update(...).execution_options(synchronize_session=False)`.
   - Assert translated domain exception cause is `StaleDataError`.
   - Assert rollback-dependent expectations for current version and persisted state.
   - References:
     - AP: `test_assessment_plan_update_translates_mapper_stale_error`, `test_assessment_plan_publish_translates_mapper_stale_error`
     - AR: `test_assessment_result_update_translates_mapper_stale_error`, `test_assessment_result_publish_translates_mapper_stale_error`

4. **Winner and snapshot assertions**
   - Verify exact persisted winner payload, final `concurrency_version`, snapshot identity, and snapshot count.
   - Apply snapshot identity/count checks where immutable version publication exists.
   - References include stale publish/no-extra-snapshot checks in both API concurrency suites.

5. **Nested-only mutation and idempotent publish coverage**
   - Nested-only mutation version advancement regression:
     - `test_assessment_result_nested_only_update_advances_concurrency_version`
   - Idempotent publication without token increment regression:
     - `test_assessment_result_idempotent_publish_reuses_snapshot_without_token_increment`

6. **API integration and frontend conflict/pending-request regressions**
   - API: stable 409 detail and 422 required-token assertions in `apps/api/tests/test_assessment_plan_api_concurrency.py` and `apps/api/tests/test_assessment_result_api_concurrency.py`.
   - Frontend: token propagation, conflict UX, pending-request disabling, unsaved-edit preservation, and explicit reload confirmation in:
     - `apps/web/tests/assessment-plan-workspace.test.tsx`
     - `apps/web/tests/assessment-result-workspace.test.tsx`

7. **Full acceptance procedure**
   - Use locked dependencies and the established PostgreSQL + frontend procedures documented in `docs/development.md`.
   - Concurrency acceptance is incomplete if these suites are not run in their intended environments.

### Why weaker evidence is insufficient

- **Thread barriers alone are insufficient:** they coordinate timing but do not prove actual database lock contention.
- **Simulated exceptions alone are insufficient:** they can prove translation logic, but not real transactional winner/loser behavior.
- **Passing tests alone are insufficient without evidence quality:** concurrency guarantees require tests that demonstrate real contention, rollback behavior, and persisted-state outcomes, not only status-code checks.



