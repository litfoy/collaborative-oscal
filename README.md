# Collaborative OSCAL

Collaborative OSCAL is the foundation of a self-hostable, open-source Governance, Risk, and Compliance (GRC) platform. The project is licensed under Apache-2.0. The product surface includes OIDC browser sign-in through a Next.js Backend-for-Frontend, a tenant-scoped **Catalog Explorer** with catalog import, basic Profile authoring, and a revision-pinned Control Implementation Register. The API provides OIDC bearer-token authentication, internal identities, tenant memberships, and tenant-scoped RBAC. Profiles select controls from exact catalog revisions; full Profile resolution is not implemented. Register status is self-reported, not an assessment. Catalog editing, assessment workflows, and evidence file storage are not implemented. See [Catalog Explorer](docs/architecture/catalog-explorer.md) for setup and [ADR 0009](docs/adr/0009-revision-safe-control-implementations.md) for register behavior and limitations.

## Architecture at a glance

The initial deployment is a modular monolith: a Next.js web app calls a FastAPI API, with PostgreSQL persistence behind tenant-scoped application services and repositories. OSCAL JSON documents are authoritative revision snapshots, while relational group/control indexes are rebuildable projections. HTTP controllers, domain rules, OSCAL handling, and optional IBM compliance-trestle integration stay at separate boundaries. A worker is reserved for future background jobs; there is no worker process or queue yet.

See [System architecture](docs/architecture/overview.md) for module boundaries and [Identity and access](docs/architecture/identity-and-access.md) for OIDC configuration, tenant authorization, Keycloak development setup, and trusted membership bootstrap. [Architecture Decision Records](docs/adr/) capture the initial choices and the questions that remain open.

The internal OSCAL Catalog import service accepts JSON or YAML and validates
Catalog documents declared as OSCAL 1.1.3, 1.2.0, 1.2.1, 1.2.2, or 1.2.3. The
authorized browser and HTTP import adapter accept JSON; the CLI also accepts YAML.
See the [Catalog import guide](docs/catalog-import.md) for compatibility,
validation limitations, security boundaries, and a development example.

## Prerequisites

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
