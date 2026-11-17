# AI Governance Demo Seed Verification (2026-11-17)

This note records lifecycle verification commands and empirical outcomes for the AI governance demo seed.

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

## 8) Remaining verification gaps

- None identified for the requested transactional-correctness scope.
- Cross-tenant verification still uses deterministic IDs inserted into the isolated database for repeatability.

## 9) Cleanup commands used

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


