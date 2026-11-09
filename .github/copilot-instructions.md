# Repository instructions

## Architecture

- Treat this repository as a modular monolith. Do not introduce services, queues, or deployment infrastructure without a demonstrated requirement.
- Keep GRC domain rules independent of FastAPI route handlers and persistence details.
- Keep OSCAL parsing, validation, serialization, and IBM compliance-trestle integration behind the `packages/oscal` boundary. Domain entities must not mirror OSCAL serialization models.
- Keep tenant identity explicit in authorization and data access designs. Never rely on client-provided tenant IDs without an authorization check.
- Authentication currently validates configured OIDC access tokens, persists external identities and tenant memberships, and exposes only `/api/v1/me`; do not imply that tenant-scoped GRC APIs, catalog management, workflows, or evidence storage are implemented.

## Implementation standards

- Use Python type annotations and Pydantic for validated API configuration/contracts; use TypeScript strict mode for the web application.
- Keep API contracts explicit and version changes intentional.
- Use environment variables for configuration. Never commit secrets, credentials, or production-like defaults.
- Apply least privilege, secure browser/API defaults, and tenant-aware isolation at each data-access boundary. Do not trust tenant IDs or roles from request headers or token claims.
- Add focused tests for behavior and run the relevant test, lint, and type-check commands before completing a change.
- Prefer maintained open-source dependencies and update lockfiles with their manifests.
- Keep changes focused; document meaningful architectural choices in `docs/adr/`.

## Current scope

The API exposes public `/health`, bearer-protected `GET /api/v1/me`, `GET /api/v1/tenants`, and read-only tenant-scoped catalog endpoints requiring `catalog:read`. OIDC access-token verification, identity/membership persistence, tenant-scoped roles, and trusted tenant-context dependencies are implemented. The Next.js app is an OIDC Backend-for-Frontend (openid-client, encrypted HttpOnly cookie session; tokens never reach the browser) hosting the read-only Catalog Explorer. Catalog import has no public endpoint (use `python -m app.cli`). GRC routes, catalog editing, profiles, public user management, and machine identities are not implemented. Control references use `catalog_id + revision_id + oscal_control_id`. See ADR 0007.
