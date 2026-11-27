# PostgreSQL database roles (ADR 0029 §8, milestone 29.1a)

Status: foundation implemented for development and tests. **Not activated** for Compose or any
installation. This milestone does not implement resource grants, actor context, the
installation gate, the participation journal or personal SoD, and makes no claim that the
ADR 0029 security architecture is complete.

## Roles

| Role | Attributes | Purpose |
|---|---|---|
| `oscal_owner` | LOGIN, NOSUPERUSER, NOCREATEROLE, NOCREATEDB, NOREPLICATION, NOBYPASSRLS, no memberships | Owns the database, the `public` schema and every object in it; runs Alembic and `apply-privileges`; owner-controlled administrative setup and test fixtures/cleanup. |
| `oscal_runtime` | as above plus NOINHERIT | Application/seed business credential with the explicit table/column privileges below. |
| `oscal_provisioner` | as above plus NOINHERIT | Isolated credential boundary for later provisioning procedures. CONNECT and schema USAGE only. |

Role names are cluster-global; use one installation per PostgreSQL cluster (or a disposable
cluster for tests).

## Operator steps

1. **Cluster-level bootstrap** (superuser, once per cluster/database):
   `DATABASE_ADMIN_URL=… OSCAL_OWNER_DB_PASSWORD=… OSCAL_RUNTIME_DB_PASSWORD=… OSCAL_PROVISIONER_DB_PASSWORD=… python -m app.persistence.database_roles bootstrap-roles`.
   Creates or normalizes the roles (distinct passwords, ≥16 characters), revokes all role
   memberships held by them, and makes `oscal_owner` the owner of the database and `public`
   schema. It refuses to run if `public` already contains objects not owned by
   `oscal_owner`: ownership transfer of an existing installation is part of the coordinated
   installation (ADR 0029 §13) and is intentionally not performed. The password is sent to
   the server in the `CREATE/ALTER ROLE` statement; do not enable statement logging during
   bootstrap.
2. **Migrations** as owner: `MIGRATION_DATABASE_URL=<oscal_owner URL> alembic -c alembic.ini upgrade head`.
   Alembic asserts the effective role is `oscal_owner` when `MIGRATION_DATABASE_URL` is used,
   and refuses to migrate as `oscal_runtime`/`oscal_provisioner` in every mode. Without
   `MIGRATION_DATABASE_URL` the legacy single-credential URL is used (transitional, logged).
3. **Privileges** as owner: `MIGRATION_DATABASE_URL=… python -m app.persistence.database_roles apply-privileges`.
   Idempotent; one transaction. Fails if any object in `public` is not owner-owned, if any
   table is unclassified or missing from `RUNTIME_TABLE_ACCESS`, or if a sequence, view or
   other non-table relation exists (none exist today; all keys are UUIDs). New migrations
   must classify their tables explicitly and rerun this step.

Owner and provisioner credentials must never be placed in the shared `.env` (loaded by the
API and BFF). `app.config.Settings` deliberately has no owner/provisioner settings.

## Effective privilege contract

Database: `PUBLIC` has no CONNECT/TEMPORARY/CREATE; runtime and provisioner have CONNECT only
(no TEMPORARY, so `pg_temp` cannot shadow objects used by trigger functions).
Schema `public`: `PUBLIC` has nothing; runtime and provisioner have USAGE, never CREATE.
Routines in `public`: no EXECUTE for `PUBLIC`, runtime or provisioner (trigger functions do
not need EXECUTE to fire). Default privileges of `oscal_owner`: no EXECUTE for `PUBLIC` on new
routines; no table, sequence or routine privileges for the business roles on new objects.
No privilege is granted WITH GRANT OPTION. TRUNCATE, REFERENCES and TRIGGER are never granted.
There are no SECURITY DEFINER functions; any future one must set a fixed `search_path`
ending in `pg_temp` (enforced by test).

| Table | Runtime | Provisioner |
|---|---|---|
| `alembic_version` | none | none |
| `tenants`, `tenant_memberships`, `organizations` | SELECT | none |
| `user_identities` | SELECT; INSERT(id, issuer, subject, display_name, email, created_at, updated_at); UPDATE(display_name, email, updated_at) | none |
| `demo_seed_runs` | SELECT, INSERT | none |
| `catalogs`, `catalog_revisions` | SELECT, INSERT; **transitional** UPDATE(updated_at) for row locks | none |
| `catalog_group_indexes`, `catalog_control_indexes` | SELECT, INSERT | none |
| `profiles`, `profile_imports`, `control_implementations`, `information_systems`, `system_components`, `system_security_plans`, `assessment_plans`, `assessment_results` | SELECT, INSERT, UPDATE | none |
| `mapping_collections`, `component_definitions` | SELECT, INSERT, UPDATE, DELETE | none |
| `mapping_members`, `implementation_responsibilities`, `component_definition_components`, `component_definition_sources` | SELECT, INSERT, DELETE | none |
| `system_security_plan_implementations` | SELECT, INSERT, DELETE; **transitional** UPDATE(created_at) for row locks | none |
| `system_security_plan_versions`, `assessment_plan_versions`, `assessment_result_versions`, `component_definition_snapshots` | SELECT, INSERT (no UPDATE/DELETE at privilege level; immutability triggers unchanged) | none |

The source of truth is `RUNTIME_TABLE_ACCESS` in `apps/api/app/persistence/database_roles.py`;
`tests/test_database_roles.py` compares it with effective privileges (`has_*_privilege`,
including PUBLIC and inheritance) on a real database.

## Remaining privilege dependencies (not resolved in 29.1a)

| Dependency | Evidence | Assigned to |
|---|---|---|
| Lock-only UPDATE columns on `catalogs`, `catalog_revisions`, `system_security_plan_implementations` (PostgreSQL requires UPDATE on a column for any `FOR UPDATE`/`FOR SHARE`). Runtime never updates these rows; draft rows' lock column remains writable. | `with_for_update` in services; `lock_*_revision` triggers | 29.1b (gate replaces locks; remove or narrow) |
| Administrative CLI commands (`create-tenant`, `bootstrap-admin`, `bootstrap-demo`) use the application `DATABASE_URL`; under separated credentials they fail closed (runtime has no tenant/membership INSERT). | `app/cli.py` | Package 2 (separate administrative job/credential) |
| `infrastructure/docker/seed-demo-catalog.py` creates `compose_demo_seeds` at runtime (needs schema CREATE) and uses a second advisory key. | script | Package 2 (Compose jobs) / 29.1b (single gate key) |
| Compose still connects API, seeds and migrations as the cluster superuser (`POSTGRES_USER`); no role bootstrap; shared credential volume. | `compose.yaml` | Package 2 activation; §13 cut-over |
| Ownership transfer of existing installations (`REASSIGN`/per-object), old credential withdrawal. | — | Package 2/5 (§13 rehearsal) |
| Runtime can change its own password (standard PostgreSQL behaviour). | — | Operational control; documented |
| Existing integration tests still use one transitional credential (`TEST_DATABASE_URL`) for fixtures and business calls; under the runtime credential 23 tests fail only due to test-side direct DML/DDL (fixture manipulation, trigger probes, migration schemas). | diagnostic run | 29.1b/29.1c test migration to owner fixtures + runtime business sessions |



