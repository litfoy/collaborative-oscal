# System architecture

## System overview

The initial system is a self-hostable modular monolith with a Next.js/React/TypeScript browser application, a Python/FastAPI/Pydantic API, and PostgreSQL. The browser calls the API health endpoint. The API has an internal tenant-aware domain and PostgreSQL persistence foundation, but it exposes no GRC endpoints and does not connect to the database during health checks or startup. A future worker belongs in the same deployment boundary until workload and operational evidence justify separation.

The implemented product surface remains health reporting only. Internal persistence operations cover initial tenant, organization, catalog revision, and derived index records; they are not user-facing capabilities. In particular, catalog import/editing, OSCAL validation, control mapping, workflow, authentication, evidence management, and continuous compliance are future work.

## Module boundaries

| Boundary | Ownership and responsibility | Current state |
|---|---|---|
| `apps/web` | User interface and browser-side API client | Minimal health page |
| `apps/api/app` | HTTP routing, configuration, application services, and persistence wiring | Health endpoint and internal GRC foundation |
| `apps/api/app/domain` | Tenant, organization, catalog/revision entities and domain invariants | Initial entities and repository interfaces |
| `apps/api/app/persistence` | PostgreSQL mappings, transactions, and tenant-scoped repositories | SQLAlchemy and Alembic foundation |
| `packages/domain` | Future cross-application domain package boundary | No separately packaged domain library |
| `packages/oscal` | OSCAL digest and catalog projections; future validation, import/export, and Trestle adapter | No full parser or schema validator |
| `packages/collaboration` | Collaboration concepts and application services | Reserved |
| `packages/automation` | Future scheduled/event-triggered jobs and policy automation | Reserved |
| `packages/authorization` | Identity integration, permissions, and tenant-scoped access decisions | Reserved |
| `apps/worker` | Future background execution entry point | Reserved |

These are logical boundaries, not separate services. Cross-module dependencies should flow through explicit application interfaces rather than importing another module's internal implementation.

## Data ownership and persistence

Business modules should own their entities, invariants, and repository interfaces. The API layer owns HTTP schemas and maps those schemas to application-level inputs/outputs; persistence models must not become public API or domain models. PostgreSQL is the planned transactional system of record. JSONB is appropriate for versioned OSCAL artifact documents and schema-dependent content, while relational columns should own identifiers, tenant associations, lifecycle metadata, and query-critical relationships. Object storage using an S3-compatible interface is deferred until evidence files are in scope.

Schema and migrations exist for the initial domain records. Database credentials remain deployment configuration; no deployment secrets are committed. The health endpoint remains independent from database availability.

## OSCAL and compliance-trestle

OSCAL is the interoperability format, not the domain model. The OSCAL boundary owns the current deterministic digest and group/control index projection and is intended to own import/export, validation, version compatibility, and canonicalization. Domain services consume stable application concepts and do not depend on generated OSCAL structures. An adapter may invoke IBM compliance-trestle behind this boundary; the adapter must remain optional so that the platform's core can be self-hosted without proprietary services. Trestle's exact supported operations, version policy, and packaging approach remain open.

## Tenant isolation

Tenant identity must be derived from a trusted authenticated principal, then passed explicitly through application and repository calls. Every tenant-owned read/write scopes by tenant; authorization must be checked at the service/data boundary, not just in the UI or route. Composite foreign keys enforce same-tenant associations in the initial shared-schema model. PostgreSQL row-level security remains a possible defense-in-depth layer, but is not enabled without authenticated tenant context and a tested policy lifecycle.

## Authentication and authorization

Authentication is not implemented. Before production deployment, select an identity model (for example, standards-based OIDC with a self-hostable identity provider), session/token handling, account lifecycle, and service-to-service identity. Authorization should be policy-based and tenant-aware, deny by default, and separate roles from resource-scoped permissions. Do not trust tenant IDs or roles supplied by an untrusted browser. A later ADR must establish threat model, identity provider compatibility, and audit requirements.

## Local development

Follow the root [README](../../README.md): copy `.env.example`, start PostgreSQL with Compose, apply migrations from `apps/api`, run the API, and run the web workspace from the repository root. Unit tests do not need a database; PostgreSQL integration tests require a dedicated database ending in `_test`. CI runs these integration tests against a PostgreSQL service.

## Security and operations

Secrets belong in local ignored environment files or a deployment secret manager. Compose binds PostgreSQL to loopback and uses a clearly development-only example password. Production requires externally managed secrets, TLS and deployment-specific network controls, backups, audit logging, monitoring, and an explicit authentication configuration; this repository does not provide production deployment hardening.

## Open architectural decisions

- Which OIDC provider/protocol profile and session architecture meet self-hosting and enterprise requirements?
- When should the initial shared-schema tenant model be supplemented by stronger
  partitioning or PostgreSQL row-level security?
- Which OSCAL versions and artifact types are first-class, and which Trestle operations should be wrapped?
- Which audit event schema, retention, and tamper-resistance requirements apply?
- What audit event schema, retention, and tamper-resistance requirements apply?
- When should evidence storage be introduced, and which S3-compatible API/features are required?
- Which background job delivery and retry semantics are required before introducing a queue?
