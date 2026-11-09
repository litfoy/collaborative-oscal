# Repository instructions

## Architecture

- Treat this repository as a modular monolith. Do not introduce services, queues, or deployment infrastructure without a demonstrated requirement.
- Keep GRC domain rules independent of FastAPI route handlers and persistence details.
- Keep OSCAL parsing, validation, serialization, and IBM compliance-trestle integration behind the `packages/oscal` boundary. Domain entities must not mirror OSCAL serialization models.
- Keep tenant identity explicit in authorization and data access designs. Never rely on client-provided tenant IDs without an authorization check.
- Do not imply that planned capabilities (GRC workflows, catalog management, authentication, persistence, or evidence storage) are implemented.

## Implementation standards

- Use Python type annotations and Pydantic for validated API configuration/contracts; use TypeScript strict mode for the web application.
- Keep API contracts explicit and version changes intentional.
- Use environment variables for configuration. Never commit secrets, credentials, or production-like defaults.
- Apply least privilege, secure browser/API defaults, and tenant-aware isolation at each future data-access boundary.
- Add focused tests for behavior and run the relevant test, lint, and type-check commands before completing a change.
- Prefer maintained open-source dependencies and update lockfiles with their manifests.
- Keep changes focused; document meaningful architectural choices in `docs/adr/`.

## Current scope

The implemented application surface is a FastAPI `/health` endpoint and a Next.js page that displays its availability. PostgreSQL is only provisioned for local development; no schema or database integration exists yet.
