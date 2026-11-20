# AI Governance Demo Seed Verification (2026-11-17)

This note records lifecycle verification commands and empirical outcomes for the AI governance demo seed.

## Supported Docker Compose startup

From the repository root:

```bash
docker compose up --build -d
```

Standard local startup now runs `python -m app.cli seed-ai-governance-demo-local`
inside `db-init` after migrations, demo identity bootstrap, and baseline catalog
import complete successfully. `api` depends on successful `db-init` completion,
and `web` depends on `api` health, so startup is blocked on seed failures.

## Troubleshooting

Check one-shot initialization completion state:

```bash
docker compose ps -a db-init
```

Inspect initialization logs for successful apply or idempotent reruns (`already applied`):

```bash
docker compose logs db-init
```

If the service exits non-zero, keep the stack running for diagnosis and review the error in logs; the failure is intentionally observable via service exit status and logs.

Manual invocation remains supported:

```bash
python -m app.cli seed-ai-governance-demo-local
```

## Seeded scenario (fictional)

All seeded content is fictional demonstration data. It is not evidence of real
compliance, certification or production readiness, and the evidence links under
`https://example.demo/fictional/` do not point to real or verified evidence.

The seed describes the **Agentic AI Development Platform**: a fictional internal
AI-assisted software development platform in which coding agents use approved
development tools to generate code and execute tests, while security-sensitive
agent actions and production releases require documented human approval. The
seed only authors documents; it adds no agent execution functionality.

Five controls from the unchanged upstream catalog are selected. Each
contribution comes from a system component adopted from the reusable safeguard
(Component Definition) that addresses that control. A contribution describes how
a component contributes to a requirement; it is not a claim that the requirement
is met.

| Control | Upstream statement (summary) | Reusable safeguard | System component | Contribution status |
| --- | --- | --- | --- | --- |
| `MG-2.2-006` | Version control for models and datasets to track changes and facilitate rollback | Model and dataset version management | Model registry and release records | partial |
| `MP-1.1-008` | Document system requirements, ownership and roles for human oversight | Human oversight of agent actions | Human approval workflow | implemented (documentation only) |
| `GV-1.2-003` | Define acceptable use policies for GAI systems | AI governance policies | AI governance policy set | partial |
| `GV-4.1-003` | Policies and procedures for risk measurement with standardized protocols and structured feedback | AI governance policies | AI governance policy set | partial |
| `MS-2.7-016` | AI red-teaming against malicious behavior | AI security testing | AI red-teaming service | partial |

The Assessment Plan defines one concrete local objective per control and three
activities. Each activity references only objectives that belong to its selected
controls, each task is linked to its activity and to the components that
contribute to the activity's controls, and the lead assessor role is linked to
its party.

The Assessment Results are deliberately narrow:

- They evaluate only the local objective `local-model-version-traceability`
  (control `MG-2.2-006`): for each of three fictional sampled releases, the
  release record must identify the exact approved model version and be matchable
  to the model registry record.
- The single observation records that two of three sampled release records met
  this and one did not. The single finding targets the local objective
  (`objective-id`) with status `not-satisfied` and references that observation.
- The finding does not conclude that `MG-2.2-006` as a whole is satisfied or not
  satisfied. The actual reviewed scope is `MG-2.2-006` only; the other four
  planned controls are not assessed, and nothing is implied about them.

The fictional assessment is dated 10 November 2026 (planned activities for the
other controls on 11 and 12 November 2026). The documents are recorded
retrospectively when the seed runs, so their publication timestamps are later
than the fictional assessment dates.

## Existing demo installations

The corrected scenario applies to fresh demo initialization only.

- A tenant that already carries the `ai-governance-demo-v1` seed marker keeps its
  original System, Component Definitions, and published SSP, Assessment Plan and
  Assessment Results versions. A repeated seed run is a no-op and never modifies,
  deletes or replaces published immutable versions.
- There is no seed migration and no automatic reset.
- To receive the corrected scenario, a pre-release local demo installation must
  be reset intentionally. This deletes **all** local demo data in that Compose
  project, including content authored manually:

  ```bash
  docker compose down -v
  docker compose up --build -d
  ```

  Do not run this against an installation whose data must be retained.

## Scope

- Investigate why `tests/test_ai_governance_demo_seed.py` was skipped.
- Execute those tests with required PostgreSQL configuration.
- Verify cross-tenant seed isolation.
- Verify seed persistence across service restart.
- Verify rollback behavior on seed failure.
- Tear down only the isolated `ai-gov-lifecycle` Compose project.

## 1) Why `test_ai_governance_demo_seed.py` was skipped

Command:

```zsh
cd /Users/rib/workspace/collaborative-oscal/apps/api
uv run pytest -q tests/test_ai_governance_demo_seed.py -rs | cat
```

Result:

- `2 skipped`.
- Skip reason from `apps/api/tests/conftest.py`: `Set TEST_DATABASE_URL to run PostgreSQL integration tests.`

## 2) Run seed tests with required PostgreSQL configuration

A temporary isolated PostgreSQL container was started for test execution:

```zsh
docker rm -f ai-gov-pytest-db >/dev/null 2>&1 || true
docker run -d --name ai-gov-pytest-db \
  -e POSTGRES_DB=collaborative_oscal_test \
  -e POSTGRES_USER=collaborative_oscal \
  -e POSTGRES_PASSWORD=collab_test_pw \
  -p 127.0.0.1:55433:5432 \
  postgres:17.11

docker exec ai-gov-pytest-db pg_isready -U collaborative_oscal -d collaborative_oscal_test | cat
```

Seed integration tests with `TEST_DATABASE_URL`:

```zsh
cd /Users/rib/workspace/collaborative-oscal/apps/api
TEST_DATABASE_URL='postgresql+psycopg://collaborative_oscal:collab_test_pw@127.0.0.1:55433/collaborative_oscal_test' \
  uv run pytest -q tests/test_ai_governance_demo_seed.py | cat
```

Result:

- `3 passed in 1.85s`.
- New coverage includes a mid-lifecycle rollback test with fault injection after multiple DB writes.

## 3) Cross-tenant seed isolation

Two additional tenants and active actors were inserted in the isolated `ai-gov-lifecycle` database:

- Tenant 2: `22222222-2222-4222-8222-222222222222`
- Actor 2: `33333333-3333-4333-8333-333333333333`
- Tenant 3: `44444444-4444-4444-8444-444444444444`
- Actor 3: `55555555-5555-4555-8555-555555555555`

Seed run for tenant 2:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle exec api /bin/sh -lc 'DEMO_AUTH_SECRET="$(cat /run/demo-credentials/demo-auth-secret)" POSTGRES_PASSWORD="$(cat /run/demo-credentials/postgres-password)" /opt/app/apps/api/.venv/bin/python -m app.cli seed-ai-governance-demo --tenant-id 22222222-2222-4222-8222-222222222222 --actor-id 33333333-3333-4333-8333-333333333333 --catalog-file /opt/demo/nist-ai-rmf-gen-ai-1.0.0-catalog.json' | cat
```

Result:

- `AI governance demo seed applied...`

Marker verification:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle exec db /bin/sh -lc 'PGPASSWORD="$(cat /run/demo-credentials/postgres-password)" psql -h 127.0.0.1 -U collaborative_oscal -d collaborative_oscal -Atc "select tenant_id, seed_name, count(*) from demo_seed_runs where seed_name = '\''ai-governance-demo-v1'\'' group by tenant_id, seed_name order by tenant_id;"' | cat
```

Result:

- `22222222-2222-4222-8222-222222222222|ai-governance-demo-v1|1`
- `86713b38-b7f0-4b6a-9c22-4e672d5cc9d4|ai-governance-demo-v1|1`

Interpretation:

- Seed marker is isolated per tenant (`tenant_id`, `seed_name`).
- Running seed in one tenant does not overwrite the other tenant's marker.

## 4) Restart persistence

API service restart:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle restart api | cat
```

Post-restart local seed command:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle exec api /bin/sh -lc 'DEMO_AUTH_SECRET="$(cat /run/demo-credentials/demo-auth-secret)" POSTGRES_PASSWORD="$(cat /run/demo-credentials/postgres-password)" /opt/app/apps/api/.venv/bin/python -m app.cli seed-ai-governance-demo-local' | cat
```

Result:

- `AI governance demo seed already applied...`

Interpretation:

- Marker persistence survives service restart; rerun remains idempotent.

## 5) Transactional rollback on seed failure

A checksum-mismatched catalog copy was created:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle exec api /bin/sh -lc 'cp /opt/demo/nist-ai-rmf-gen-ai-1.0.0-catalog.json /tmp/nist-ai-rmf-gen-ai-1.0.0-catalog.bad.json && printf "\n" >> /tmp/nist-ai-rmf-gen-ai-1.0.0-catalog.bad.json && ls -l /tmp/nist-ai-rmf-gen-ai-1.0.0-catalog.bad.json' | cat
```

Seed invoked for tenant 3 with bad catalog:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle exec api /bin/sh -lc 'DEMO_AUTH_SECRET="$(cat /run/demo-credentials/demo-auth-secret)" POSTGRES_PASSWORD="$(cat /run/demo-credentials/postgres-password)" /opt/app/apps/api/.venv/bin/python -m app.cli seed-ai-governance-demo --tenant-id 44444444-4444-4444-8444-444444444444 --actor-id 55555555-5555-4555-8555-555555555555 --catalog-file /tmp/nist-ai-rmf-gen-ai-1.0.0-catalog.bad.json' | cat
```

Result:

- Command failed with `Upstream AI RMF catalog checksum mismatch.`

Post-failure persistence check:

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle exec db /bin/sh -lc 'PGPASSWORD="$(cat /run/demo-credentials/postgres-password)" psql -h 127.0.0.1 -U collaborative_oscal -d collaborative_oscal -Atc "select (select count(*) from demo_seed_runs where tenant_id = '\''44444444-4444-4444-8444-444444444444'\'' and seed_name = '\''ai-governance-demo-v1'\'') as marker_count, (select count(*) from information_systems where tenant_id = '\''44444444-4444-4444-8444-444444444444'\'' and name = '\''Agentic AI Development Platform'\'') as system_count, (select count(*) from catalog_revisions where tenant_id = '\''44444444-4444-4444-8444-444444444444'\'') as catalog_revision_count;"' | cat
```

Result:

- `0|0|0`

Interpretation:

- No marker, system, or catalog revision was persisted for the failing tenant.

## 6) Mid-lifecycle transactional rollback (fault injection)

Implementation:

- Added PostgreSQL integration test `test_ai_governance_demo_seed_rolls_back_mid_lifecycle_failure` in `apps/api/tests/test_ai_governance_demo_seed.py`.
- The test monkeypatches `app.application.ai_governance_demo._validate_historical_chain` to raise `RuntimeError("Injected failure after seed resource writes.")`.
- Injection point is after catalog import, component definitions, system/components, SSP/AP/AR drafts, and immutable version creation; this occurs before outer transaction commit.

Command:

```zsh
cd /Users/rib/workspace/collaborative-oscal/apps/api
TEST_DATABASE_URL='postgresql+psycopg://collaborative_oscal:collab_test_pw@127.0.0.1:55433/collaborative_oscal_test' \
  uv run pytest -q tests/test_ai_governance_demo_seed.py | cat
```

Result:

- `3 passed in 1.85s`.
- During the injected failure run, a fresh session observed zero rows for tenant-scoped seed artifacts:
  - marker (`demo_seed_runs`), catalogs, catalog revisions, catalog controls,
  - information systems, system components,
  - component definitions/components/snapshots,
  - implementations,
  - SSP + SSP versions + SSP implementation links,
  - Assessment Plans + versions,
  - Assessment Results + versions.
- Baseline tenant data (tenant membership footprint and global identity count) remained unchanged.
- After removing the monkeypatch, the same tenant seed run succeeded, and a subsequent run returned an idempotent no-op.

## 7) Regression tests run

```zsh
cd /Users/rib/workspace/collaborative-oscal/apps/api
TEST_DATABASE_URL='postgresql+psycopg://collaborative_oscal:collab_test_pw@127.0.0.1:55433/collaborative_oscal_test' \
  uv run pytest -q tests/test_compose_seed.py tests/test_ai_governance_demo_seed.py | cat
```

Result:

- `6 passed in 2.00s`.

## 8) Semantic regression coverage of the published chain

`test_ai_governance_demo_seed_publishes_semantically_consistent_chain` in
`apps/api/tests/test_ai_governance_demo_seed.py` seeds a fresh tenant and checks
the published documents rather than object counts:

- Trestle model and official JSON Schema validity of the published SSP,
  Assessment Plan, Assessment Results and Component Definition snapshots.
- The five approved controls, and that each contribution's component is adopted
  from the safeguard that addresses that control (security testing separate from
  human oversight).
- Distinct contribution descriptions and evidence references, and aligned
  register status, OSCAL status and status remarks.
- The control of the local model-version objective, and that every activity
  references only objectives belonging to its selected controls.
- Task-to-activity, task-to-subject and role-to-party links.
- Actual reviewed scope, finding target type and ID, existence of the targeted
  objective in the pinned Assessment Plan, related observations, evidence
  resources, and a consistent fictional timeline.
- Pinned historical references along catalog revision, SSP version, Assessment
  Plan version and Assessment Results version, and unchanged published versions
  after a repeated seed run.

With this test the focused seed test file contains four tests (sections 2, 6 and
7 above record the earlier three-test runs).

## 9) Remaining verification gaps

- None identified for the requested transactional-correctness scope.
- Cross-tenant verification still uses deterministic IDs inserted into the isolated database for repeatability.
- The seeded scenario has not been verified through the graphical user interface.

## 10) Cleanup commands used

Isolated lifecycle stack cleanup (executed with explicit project name only):

```zsh
cd /Users/rib/workspace/collaborative-oscal
docker compose -p ai-gov-lifecycle down -v | cat
```

Temporary PostgreSQL test container cleanup:

```zsh
docker rm -f ai-gov-pytest-db | cat
```

These commands target only `ai-gov-lifecycle` and `ai-gov-pytest-db`; no commands were run against the default Compose project name.



