# Collaborative OSCAL

Collaborative OSCAL is the foundation of a self-hostable, open-source Governance, Risk, and Compliance (GRC) platform. The project is licensed under Apache-2.0. The product surface includes OIDC browser sign-in through a Next.js Backend-for-Frontend, a tenant-scoped **Catalog Explorer** with catalog import, basic Profile authoring, and a revision-pinned Control Implementation Register. The API provides OIDC bearer-token authentication, internal identities, tenant memberships, and tenant-scoped RBAC. Profiles select controls from exact catalog revisions; full Profile resolution is not implemented. Register status is self-reported, not an assessment. Catalog editing, assessment workflows, and evidence file storage are not implemented. See [Catalog Explorer](docs/architecture/catalog-explorer.md) for setup and [ADR 0009](docs/adr/0009-revision-safe-control-implementations.md) for register behavior and limitations.

## Architecture at a glance

The initial deployment is a modular monolith: a Next.js web app calls a FastAPI API, with PostgreSQL persistence behind tenant-scoped application services and repositories. OSCAL JSON documents are authoritative revision snapshots, while relational group/control indexes are rebuildable projections. HTTP controllers, domain rules, OSCAL handling, and optional IBM compliance-trestle integration stay at separate boundaries. A worker is reserved for future background jobs; there is no worker process or queue yet.

See [System architecture](docs/architecture/overview.md) for module boundaries and [Identity and access](docs/architecture/identity-and-access.md) for OIDC configuration, tenant authorization, Keycloak development setup, and trusted membership bootstrap. [Architecture Decision Records](docs/adr/) capture the initial choices and the questions that remain open.

The internal OSCAL Catalog import service accepts JSON or YAML and validates
Catalog documents declared as OSCAL 1.0.0–1.0.6, 1.1.0–1.1.3, or 1.2.0–1.2.3. The
authorized browser and HTTP import adapter accept JSON; the CLI also accepts YAML.
See the [Catalog import guide](docs/catalog-import.md) for compatibility,
validation limitations, security boundaries, and a development example.

## Zero-configuration demo

With Docker and Docker Compose v2 installed, run from the repository root:

```sh
docker compose up
```

Once startup completes, open **http://localhost:3000**. The first run builds the
application images, generates server-only credentials, starts PostgreSQL, applies
the migrations, and creates the Acme Corp demo workspace. No `.env` file or
Keycloak is needed. The workspace starts empty: use Catalog Explorer to import
an OSCAL Catalog JSON file, for example
`examples/catalogs/sample-data-handling.json`.

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

   Open `http://localhost:3000`. Signing in requires the OIDC and session variables from `.env.example` (see [Catalog Explorer](docs/architecture/catalog-explorer.md#local-setup)). `API_BASE_URL` points the Next.js server at the API; the web scripts load this root environment file.

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

## Tests and checks

Run backend unit tests and lint:

```sh
cd apps/api
uv run pytest
uv run ruff check .
```

PostgreSQL integration tests require a dedicated PostgreSQL database whose name ends
with `_test`; they never use SQLite. With the local Compose database running, create
the test database with:

```sh
docker compose --env-file .env -f infrastructure/docker/compose.yaml exec -T db \
  sh -c 'createdb -U "$POSTGRES_USER" collaborative_oscal_test'
```

Export `TEST_DATABASE_URL` with the same connection details as `DATABASE_URL` (or
the `POSTGRES_*` settings) but with the database name `collaborative_oscal_test`,
then run `uv run pytest` from `apps/api`. The migration integration test upgrades,
downgrades, and reapplies the schema in that test database.

Run frontend lint and type checking from the repository root:

```sh
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run test
```

GitHub Actions runs the PostgreSQL integration tests against a dedicated PostgreSQL
service as well as the health/unit and lint checks.

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
helpers. See [Copilot repository instructions](.github/copilot-instructions.md) for
coding and architecture conventions.
