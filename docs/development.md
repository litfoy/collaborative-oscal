# Developer guide

This guide covers setup, development, and technical details. For the project
overview, see the [English README](../README.md) or the
[German README](../README.de.md).

The project is licensed under Apache-2.0. Its current product surface includes
OIDC browser sign-in through a Next.js Backend-for-Frontend, a tenant-scoped
**Catalog Explorer** with command-line catalog import, basic Profile authoring,
and a revision-pinned Control Implementation Register. It also includes
Assessment Plan authoring pinned to immutable SSP versions, with explicit
assessment scope/objective/subject/activity/task planning and immutable
OSCAL Assessment Plan exports. The API provides OIDC
bearer-token authentication, internal identities, tenant memberships, and
tenant-scoped RBAC. Profiles select controls from exact catalog revisions; full
Profile resolution is not implemented. Register status is self-reported, not an
assessment outcome. Catalog editing, Assessment Results workflows, and evidence
file storage are not implemented. See [Catalog Explorer](architecture/catalog-explorer.md)
for setup and [ADR 0009](adr/0009-revision-safe-control-implementations.md) for
register behavior and limitations.

## Architecture at a glance

The initial deployment is a modular monolith: a Next.js web app calls a FastAPI API, with PostgreSQL persistence behind tenant-scoped application services and repositories. OSCAL JSON documents are authoritative revision snapshots, while relational group/control indexes are rebuildable projections. HTTP controllers, domain rules, OSCAL handling, and optional IBM compliance-trestle integration stay at separate boundaries. A worker is reserved for future background jobs; there is no worker process or queue yet.

See [System architecture](architecture/overview.md) for module boundaries and [Identity and access](architecture/identity-and-access.md) for OIDC configuration, tenant authorization, Keycloak development setup, and trusted membership bootstrap. [Architecture Decision Records](adr/) capture the initial choices and the questions that remain open.

The internal OSCAL Catalog import service accepts JSON or YAML and validates
Catalog documents declared as OSCAL 1.0.0–1.0.6, 1.1.0–1.1.3, or 1.2.0–1.2.3. The
authorized browser and HTTP import adapter accept JSON; the CLI also accepts YAML.
See the [Catalog import guide](catalog-import.md) for compatibility,
validation limitations, security boundaries, and a development example.

## Zero-configuration demo

With Docker and Docker Compose v2 installed, run from the repository root:

```sh
docker compose up
```

Once startup completes, open **http://localhost:3000**. The first run builds the
application images, generates server-only credentials, starts PostgreSQL, applies
the migrations, and creates the Acme Corp demo workspace. No `.env` file or
Keycloak is needed. The workspace includes the official NIST SP 800-53 Rev. 5.2.0
catalog; use Catalog Explorer to browse it or import other OSCAL Catalog JSON
files, for example `examples/catalogs/sample-data-handling.json`. The bundled
NIST catalog is imported once per demo database; restarts do not replace changes
or re-import a catalog that was later removed. After updating an existing checkout,
run `docker compose up --build` to rebuild its images; existing demo databases
then acquire the seed unless they already contain that OSCAL document.

This is **only a local demonstration**, not a production deployment. Anyone who
can access the frontend can act as the demo user and make changes. Only the
frontend is published, on localhost; the API and database use the Compose
network. Do not expose this stack publicly or connect it to production data.

Generated credentials and database data are kept in separate named volumes.
`docker compose stop` / `docker compose start` and `docker compose down` /
`docker compose up` retain both. To reset the demo completely, run:

```sh
docker compose down -v
```

**Warning:** this permanently deletes the Compose-managed demo database and
generated credentials. Back up both volumes together if retaining the database;
if the database credential is missing while data exists, startup fails instead of
silently generating an incompatible password.

## Manual development prerequisites

- Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 22.13+ and npm 10
- Docker Compose v2

The application pins compatible dependency ranges in `apps/api/pyproject.toml` and `apps/web/package.json`; `apps/api/uv.lock` and `package-lock.json` capture resolved versions. The current stack targets FastAPI 0.162, Pydantic 2.14, Next.js 16.4, React 19.3, TypeScript 5.9, ESLint 10, and PostgreSQL 17.11. See each manifest and lockfile for the exact patch versions.

## Local development

1. Copy the example environment file. Its database password is a local-development placeholder and must not be used in a deployed environment.

   ```sh
   cp .env.example .env
   ```

2. Start PostgreSQL (published on localhost only):

   ```sh
   docker compose --env-file .env -f infrastructure/docker/compose.yaml up -d db
   ```

3. In a terminal, install the API dependencies and run FastAPI:

   ```sh
   cd apps/api
   uv sync
   uv run uvicorn app.main:app --reload
   ```

   Apply the initial schema from `apps/api`:

   ```sh
   uv run alembic -c ../../alembic.ini upgrade head
   ```

   The health endpoint is `http://localhost:8000/health`; interactive API documentation is at `http://localhost:8000/docs`. Database configuration uses `DATABASE_URL` when provided, otherwise the `POSTGRES_*` variables from `.env`. The health endpoint does not depend on the database.

4. In another terminal, install the web dependencies and start Next.js:

   ```sh
   npm ci
   npm --workspace apps/web run dev
   ```

   Open `http://localhost:3000`. Signing in requires the OIDC and session variables from `.env.example` (see [Catalog Explorer](architecture/catalog-explorer.md#local-setup)). `API_BASE_URL` points the Next.js server at the API; the web scripts load this root environment file.

Stop PostgreSQL with `docker compose --env-file .env -f infrastructure/docker/compose.yaml down`. Add `-v` only when intentionally deleting the local database volume.

### Local demo without Keycloak

Demo mode is **only for local development and controlled demonstrations**. Anyone
who can reach its login-free frontend can act as the Demo User, including making
changes. Never expose it publicly or connect it to production data. Use a dedicated
non-production PostgreSQL database and bind the web app and API to loopback.
URL checks do not establish network isolation.

1. In the ignored `.env`, set `AUTH_MODE=demo` and set `DEMO_AUTH_SECRET` to the
   output of `openssl rand -hex 32`. The same server-only secret must be available
   to both web and API processes. Never use a `NEXT_PUBLIC_` variable, commit it,
   or send it to a browser.
2. Set `DATABASE_URL` to the dedicated demo database and apply the existing
   migrations. Run the operator-controlled bootstrap from `apps/api`:

   ```sh
   uv run alembic -c ../../alembic.ini upgrade head
   uv run python -m app.cli bootstrap-demo
   ```

   Bootstrap is transactional and repeatable; conflicting existing records cause
   an error instead of being changed. It creates no catalogs or other business
   content. Optional content can be imported separately.
3. Keep `APP_PUBLIC_URL=http://localhost:3000` and bind both servers to loopback:

   ```sh
   # From apps/api:
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   # From the repository root, in a separate terminal:
   npm --workspace apps/web run dev -- --hostname 127.0.0.1
   ```

   `API_BASE_URL` is a server-side destination;
   it may use an internal service address such as `http://api:8000` in an
   isolated deployment. Protect that network and the credential in transit.
   Open the app to enter the Acme Corp workspace as Demo User. The fixed
   `catalog_editor` membership retains normal tenant and permission checks.

Unset demo settings or set `AUTH_MODE=keycloak` to return to the existing OIDC
flow. Authentication failures never switch modes.

## Frontend localization

English (`en`) is the default; German (`de`) can be selected in the application
header, including before sign-in. The independent `co_locale` preference cookie
persists for one year across navigation, reloads, sign-out, and subsequent visits.
Both languages are bundled in the normal web image: no environment setting,
database migration, or language-specific rebuild is required.

Resources live in `apps/web/src/lib/i18n/`. Add stable, area-prefixed keys to the
appropriate English dictionary and the corresponding German dictionary. German
keys are checked by TypeScript; `tests/i18n.test.tsx` checks key and interpolation
parameter parity. A missing German entry falls back to English at runtime.
Use `const { t, number, date, enumLabel } = useI18n()` in Client Components, or
`await getI18n()` from `@/lib/i18n/server` in Server Components. Interpolation uses
named placeholders, for example `t("common.page", { page: number(page),
pages: number(pages) })`. Use separate singular/plural keys for counts.

Use `enumLabel(storedValue)` for known human-readable enum labels, adding
`enums.<official-value>` entries in `common.ts` when needed. Never replace option
values or API payload values with translated labels. Keep official mapping
relationship identifiers accessible. Unknown enum values remain visible verbatim.
Use native locale-aware helpers for display only; timestamps are presented in
UTC consistently during SSR and hydration.

Frontend-generated validation messages belong in the dictionaries. Map backend
errors by existing stable kinds/codes only. If a diagnostic has no stable mapping,
keep its original text, code, identifiers, and validation paths with localized
surrounding context. Do not parse English backend messages to translate them.
Never pass imported Catalog content, OSCAL metadata, user-authored descriptions,
or exports through translation lookup. See
[ADR 0018](adr/0018-frontend-internationalization.md).

For mutable aggregate concurrency behavior, follow [ADR 0022](adr/0022-aggregate-optimistic-concurrency.md)
and the implementation/verification guide at
[docs/architecture/optimistic-concurrency.md](architecture/optimistic-concurrency.md).

## Tests and checks

Run backend unit tests and lint:

```sh
cd apps/api
uv run pytest
uv run ruff check .
```

PostgreSQL integration tests require a dedicated PostgreSQL database whose name ends
with `_test`; they never use SQLite. Prefer an isolated, disposable PostgreSQL
instance, separate from the demo database and its volumes:

```sh
docker run --rm --name collaborative-oscal-integration-test \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=collaborative_oscal_test \
  -p 127.0.0.1:55432:5432 -d postgres:17.11
docker exec collaborative-oscal-integration-test pg_isready -U postgres
# Wait for pg_isready to succeed before running pytest.
cd apps/api
TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55432/collaborative_oscal_test \
  uv run --locked pytest -ra
# When finished:
docker stop collaborative-oscal-integration-test
```

Trust authentication is only for this disposable, loopback-bound test instance.
Never use it for the demo or a deployed database. The suite upgrades the dedicated
database to head; migration tests also exercise upgrade/downgrade sequences in
transactional, isolated schemas and roll them back. Never point
`TEST_DATABASE_URL` at a database containing data you need to retain.

Run frontend lint and type checking from the repository root:

```sh
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run test
```

GitHub Actions runs linting and non-integration API tests on pushes and pull requests.
PostgreSQL integration tests run only on pull requests, against a dedicated PostgreSQL
service. Changes pushed directly to a branch without a pull request do not run the
integration tests.

### Verified integration baseline (2026-11-17)

The complete API suite with a fresh, dedicated PostgreSQL 17 database passes:
**289 passed, 0 failed, 0 errors, 0 skipped**. There are no remaining integration
blockers or compatibility-policy exceptions. Frontend regression checks also pass:
154 tests, ESLint, and TypeScript; API Ruff checks pass.

Downgrading a populated database can intentionally stop before `base` to prevent
data loss. In particular, migration `71bc92de4a10` raises a protective runtime
error when Profile-import provenance rows exist, so full downgrade/re-upgrade
verification should run against a fresh disposable database.

The unmodified authoring-consolidation commit `ae57eb4` reproduced 228 passed,
7 failed, and 25 setup errors. Its predecessor `7f2598f`, run in a separate Git
worktree with its own database and locked dependencies, reproduced the same seven
failures and 25 errors (214 passed, 8 failed total; its additional failure was an
SSP schema digest assertion already corrected by `ae57eb4`).

| Root cause | Correction and evidence |
|---|---|
| Invalid synthetic Catalog | `sample-security-practices.json` declares OSCAL 1.2.1. `/catalog/groups/0` contained `controls` with `ac-1` and `ac-2` alongside `groups` containing `ac-priv`. The official NIST 1.2.1 schema requires these alternatives to be mutually exclusive. Trestle rejected `Group1/controls` and `Group2/groups` as `extra_forbidden`; this was not a Trestle compatibility limitation. Moving `ac-priv` to a sibling group preserves all control IDs and content. A regression checks both Trestle and the official declared-version schema, without changing version dispatch. This removed all 25 setup errors. |
| Incorrect hierarchy assertions | The persistence fixture places `ac-1` and its child `ac-1.1` inside the nested Account Management group, not the outer Access Control group. Assertions now identify the actual group and parent control rather than relying on unordered query results. Revision/path-derived identities remain unchanged. Explorer assertions reflect the corrected synthetic Catalog and still exercise nested groups through the existing nested-group fixture. |
| Malformed fixture path | The duplicate-control rollback test addressed controls directly beneath the outer group. It now duplicates a control at the fixture's actual nested path and still requires the database integrity failure and complete rollback. |
| Broken migration downgrade | Migration `ed72a1c94b30` created `uq_system_components_this_system` but dropped nonexistent `ix_system_components_this_system`. With explicit approval, only that downgrade name was corrected; upgrade behavior and deployed schemas are unchanged. Fresh upgrade, full downgrade, re-upgrade, populated profile migration, and its intentional data-loss downgrade rejection pass. |
| Incorrect trigger exception expectation | The Component Definition revision guard uses PostgreSQL `RAISE EXCEPTION` without an explicit integrity SQLSTATE. Psycopg reports `RaiseException`, SQLSTATE `P0001`, wrapped by SQLAlchemy as `ProgrammingError`. The assertion requires that exact exception, SQLSTATE, guard message, and function context, then verifies revision content, digest, timestamp, and the Component Definition remain unchanged. No trigger was changed. |
| Missing audit log capture | Alembic's `fileConfig` disabled already-imported application loggers. Keeping existing loggers enabled restores actual audit logging, rather than weakening the log assertion. |
| Stale authoring-version assertions | Four Catalog API scenarios, previously hidden by fixture setup errors, still expected authored Profiles or Mappings to use 1.2.3. They now require the approved 1.2.1 policy; explicit legacy-version preservation assertions remain intact. Three Profile scenarios pass unchanged on the predecessor after correcting only the synthetic fixture, confirming these stale assertions were introduced by the consolidation. |
| Related-mapping response serialization | Pydantic response conversion received `RelatedControl` dataclasses without attribute-based validation enabled. The response model now supports those attributes, consistent with existing response models, and the integration test checks complete source/target provenance. This failure also reproduces on the predecessor with only the synthetic fixture corrected. |
| Local authentication configuration leakage | Catalog API tests now explicitly select their OIDC authentication mode, so a developer's ignored demo `.env` cannot bypass the stub token validator and cause unrelated 401 responses. |
| Same-second Component Definition lifecycle | The existing update correction advances second-resolution `last-modified` monotonically. Deleting a component now uses the same rule instead of potentially moving time backwards. A frozen-clock regression verifies new document UUIDs and versions for real changes, stable component UUIDs, unchanged no-op updates and repeated exports, and valid OSCAL output. |

No normative Catalogs, historical SSP versions, adoption snapshots, dependency
locks, or authoring-version policies were changed. No tests were skipped and no
schema-only fallback was introduced.

## Repository layout

```text
apps/
  api/                 FastAPI application and API tests
  web/                 Next.js application
  worker/              Reserved; background processing is not implemented
packages/
  domain/              Domain boundary documentation
  oscal/               Installable OSCAL document/projection boundary
  collaboration/       Collaboration boundary
  automation/          Automation boundary
  authorization/       Tenant-aware authorization boundary
infrastructure/docker/ Local PostgreSQL Compose configuration
docs/architecture/     System architecture and operating principles
docs/adr/              Initial architecture decisions
.github/               Repository instructions and CI workflow
tests/                 Reserved for future cross-module integration tests
```

Remaining package boundary documents describe future ownership and are not implemented
product features. The OSCAL package currently contains only digest and projection
helpers. See [Copilot repository instructions](../.github/copilot-instructions.md) for
coding and architecture conventions.
