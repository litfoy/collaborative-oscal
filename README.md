# Collaborative OSCAL

Collaborative OSCAL is the foundation of a self-hostable, open-source Governance, Risk, and Compliance (GRC) platform. The project is licensed under Apache-2.0. This repository currently contains only a runnable application foundation and a backend health check; it does **not** implement GRC, OSCAL catalog management, authentication, workflow, or evidence features.

## Architecture at a glance

The initial deployment is a modular monolith: a Next.js web app calls a FastAPI API, with PostgreSQL available as the persistence service. Business capabilities are intended to remain in independent domain modules, while HTTP controllers, OSCAL serialization, and optional IBM compliance-trestle integration stay at their respective boundaries. A worker is reserved for future background jobs; there is no worker process or queue yet.

See [System architecture](docs/architecture/overview.md) for module boundaries, data ownership, OSCAL integration, tenant isolation, and authentication strategy. [Architecture Decision Records](docs/adr/) capture the initial choices and the questions that remain open.

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

   The health endpoint is `http://localhost:8000/health`; interactive API documentation is at `http://localhost:8000/docs`. PostgreSQL is provisioned for future persistence; the health endpoint does not connect to it yet.

4. In another terminal, install the web dependencies and start Next.js:

   ```sh
   npm ci
   npm --workspace apps/web run dev
   ```

   Open `http://localhost:3000`. The page requests the backend health endpoint. Set `NEXT_PUBLIC_API_BASE_URL` in `.env` to override the default `http://localhost:8000`; the web scripts load this root environment file.

Stop PostgreSQL with `docker compose --env-file .env -f infrastructure/docker/compose.yaml down`. Add `-v` only when intentionally deleting the local database volume.

## Tests and checks

Run backend tests and lint:

```sh
cd apps/api
uv run pytest
uv run ruff check .
```

Run frontend lint and type checking from the repository root:

```sh
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
```

The GitHub Actions workflow runs these same checks and verifies the API tests. It does not require PostgreSQL because no database behavior is implemented yet.

## Repository layout

```text
apps/
  api/                 FastAPI application and API tests
  web/                 Next.js application
  worker/              Reserved; background processing is not implemented
packages/
  domain/              Domain boundary
  oscal/               OSCAL and Trestle adapter boundary
  collaboration/       Collaboration boundary
  automation/          Automation boundary
  authorization/       Tenant-aware authorization boundary
infrastructure/docker/ Local PostgreSQL Compose configuration
docs/architecture/     System architecture and operating principles
docs/adr/              Initial architecture decisions
.github/               Repository instructions and CI workflow
tests/                 Reserved for future cross-module integration tests
```

Package boundary documents describe intended ownership; they are not implemented product features. See [Copilot repository instructions](.github/copilot-instructions.md) for coding and architecture conventions.
