# System architecture

## System overview

The initial system is a self-hostable modular monolith with a Next.js/React/TypeScript browser application, a Python/FastAPI/Pydantic API, and PostgreSQL. The browser calls the public health endpoint. The API has a protected `/api/v1/me` identity endpoint and an internal tenant-aware domain and PostgreSQL persistence foundation; it exposes no GRC endpoints and does not connect to the database during health checks or startup. A future worker belongs in the same deployment boundary until workload and operational evidence justify separation.

The implemented HTTP product surface is public health reporting and a protected identity endpoint. Internal application services support tenant, organization, catalog revision, derived index, and OSCAL Catalog import/validation operations; none are exposed as user-facing GRC endpoints. Catalog editing, control mapping, workflow, evidence management, and continuous compliance are future work.

## Module boundaries

| Boundary | Ownership and responsibility | Current state |
|---|---|---|
| `apps/web` | User interface and browser-side API client | Minimal health page |
| `apps/api/app` | HTTP routing, OIDC token verification, configuration, application services, and persistence wiring | Public health, protected identity endpoint, and internal GRC foundation |
| `apps/api/app/domain` | Tenant, organization, catalog/revision entities and domain invariants | Initial entities and repository interfaces |
| `apps/api/app/persistence` | PostgreSQL mappings, transactions, and tenant-scoped repositories | SQLAlchemy and Alembic foundation |
| `packages/domain` | Future cross-application domain package boundary | No separately packaged domain library |
| `packages/oscal` | OSCAL digest, catalog projections, safe JSON/YAML parser, versioned schema and Trestle Catalog model validation | Internal Catalog import validation for OSCAL 1.1.3 and 1.2.1 |
| `packages/collaboration` | Collaboration concepts and application services | Reserved |
| `packages/automation` | Future scheduled/event-triggered jobs and policy automation | Reserved |
| `packages/authorization` | Future separately packaged authorization boundary | Documentation only; current implementation is in `apps/api/app` |
| `apps/worker` | Future background execution entry point | Reserved |

These are logical boundaries, not separate services. Cross-module dependencies should flow through explicit application interfaces rather than importing another module's internal implementation.

## Data ownership and persistence

Business modules should own their entities, invariants, and repository interfaces. The API layer owns HTTP schemas and maps those schemas to application-level inputs/outputs; persistence models must not become public API or domain models. PostgreSQL is the planned transactional system of record. JSONB is appropriate for versioned OSCAL artifact documents and schema-dependent content, while relational columns should own identifiers, tenant associations, lifecycle metadata, and query-critical relationships. Object storage using an S3-compatible interface is deferred until evidence files are in scope.

Schema and migrations exist for the initial domain records. Database credentials remain deployment configuration; no deployment secrets are committed. The health endpoint remains independent from database availability.

## OSCAL and compliance-trestle

OSCAL is the interoperability format, not the domain model. The OSCAL boundary owns deterministic digests, group/control index projections, safe JSON/YAML parsing, and versioned Catalog validation. The internal import application service coordinates tenant-scoped persistence without exposing an HTTP route. It validates OSCAL Catalog 1.1.3 and 1.2.1. Trestle model validation does not claim exhaustive NIST Metaschema semantic validation; see [Catalog import](../catalog-import.md). Domain services consume stable application concepts and do not depend on generated OSCAL structures.

## Tenant isolation

Tenant identity must be derived from a verified OIDC access token and an active database membership, then passed explicitly through application and repository calls. Every tenant-owned read/write scopes by tenant; authorization must be checked at the service/data boundary, not just in the UI or route. Composite foreign keys enforce same-tenant associations in the initial shared-schema model. The reusable tenant dependency constructs an authorized context from the selected tenant and a current membership lookup; it does not trust a tenant header or token claim. PostgreSQL row-level security remains a possible defense-in-depth layer, but is not enabled without a tested policy lifecycle.

## Authentication and authorization

OIDC access-token verification, provider-neutral application identities, database-backed tenant memberships, tenant-scoped RBAC, and reusable FastAPI dependencies are implemented. Keycloak is the optional local reference provider; no Keycloak dependency appears in domain or application code. Only `/api/v1/me` is exposed, and it does not require tenant membership. No catalog or other tenant GRC endpoint exists yet. See [Identity and access](identity-and-access.md) for the token profile, configuration, authorization boundary, local provider setup, bootstrap operation, and limitations. Production deployments still need operational secrets, TLS, log retention, and provider-specific profile review.

## Local development

Follow the root [README](../../README.md): copy `.env.example`, start PostgreSQL with Compose, apply migrations from `apps/api`, run the API, and run the web workspace from the repository root. The optional local Keycloak service and development access-token flow are documented in [Identity and access](identity-and-access.md). Unit tests do not need a database; PostgreSQL integration tests require a dedicated database ending in `_test`. CI runs these integration tests against a PostgreSQL service.

## Security and operations

Secrets belong in local ignored environment files or a deployment secret manager. Compose binds PostgreSQL and optional development Keycloak to loopback. Production requires externally managed secrets, TLS and deployment-specific network controls, backups, audit-log retention, monitoring, and provider-specific access-token profile configuration; this repository does not provide production deployment hardening.

## Open architectural decisions

- When should the initial shared-schema tenant model be supplemented by stronger
  partitioning or PostgreSQL row-level security?
- Which OSCAL versions and artifact types are first-class, and which Trestle operations should be wrapped?
- What audit event schema, retention, and tamper-resistance requirements apply?
- When should evidence storage be introduced, and which S3-compatible API/features are required?
- Which background job identity and permission lifecycle are required before introducing automation?
