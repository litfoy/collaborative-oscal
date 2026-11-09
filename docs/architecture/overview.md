# System architecture

## System overview

The initial system is a self-hostable modular monolith with a Next.js/React/TypeScript browser application, a Python/FastAPI/Pydantic API, and PostgreSQL provisioned for local development. The browser calls the API health endpoint. PostgreSQL is not yet connected to the API. A future worker belongs in the same deployment boundary until workload and operational evidence justify separation.

No product capability beyond health reporting is implemented. In particular, catalog management, OSCAL import/export, control mapping, workflow, authentication, evidence management, and continuous compliance are future work.

## Module boundaries

| Boundary | Ownership and responsibility | Current state |
|---|---|---|
| `apps/web` | User interface and browser-side API client | Minimal health page |
| `apps/api` | HTTP routing, API configuration, and transport contracts | Health endpoint only |
| `packages/domain` | GRC concepts and business invariants, independent of HTTP and OSCAL | Reserved |
| `packages/oscal` | Canonical OSCAL artifact handling, validators, import/export, and Trestle adapter | Reserved |
| `packages/collaboration` | Collaboration concepts and application services | Reserved |
| `packages/automation` | Future scheduled/event-triggered jobs and policy automation | Reserved |
| `packages/authorization` | Identity integration, permissions, and tenant-scoped access decisions | Reserved |
| `apps/worker` | Future background execution entry point | Reserved |

These are logical boundaries, not separate services. Cross-module dependencies should flow through explicit application interfaces rather than importing another module's internal implementation.

## Data ownership and persistence

Business modules should own their entities, invariants, and repository interfaces. The API layer owns HTTP schemas and maps those schemas to application-level inputs/outputs; persistence models must not become public API or domain models. PostgreSQL is the planned transactional system of record. JSONB is appropriate for versioned OSCAL artifact documents and schema-dependent content, while relational columns should own identifiers, tenant associations, lifecycle metadata, and query-critical relationships. Object storage using an S3-compatible interface is deferred until evidence files are in scope.

No schema, migrations, database credentials for deployment, or persistence code currently exist.

## OSCAL and compliance-trestle

OSCAL is the interoperability format, not the domain model. The OSCAL boundary will own import/export, validation, version compatibility, and JSON canonicalization. Domain services should consume stable application concepts and should not depend on generated OSCAL structures. An adapter may invoke IBM compliance-trestle behind this boundary; the adapter must remain optional so that the platform's core can be self-hosted without proprietary services. Trestle's exact supported operations, version policy, and packaging approach remain open.

## Tenant isolation

Tenant identity must be derived from a trusted authenticated principal, then passed explicitly through application and repository calls. Every tenant-owned read/write must scope by tenant; authorization must be checked at the service/data boundary, not just in the UI or route. PostgreSQL row-level security is a possible defense-in-depth layer, but it does not replace application checks. The initial schema and isolation model (shared schema with tenant keys versus stronger database/schema separation) require an ADR before persistent multi-tenant features are implemented. The current foundation has no tenants or tenant data.

## Authentication and authorization

Authentication is not implemented. Before production deployment, select an identity model (for example, standards-based OIDC with a self-hostable identity provider), session/token handling, account lifecycle, and service-to-service identity. Authorization should be policy-based and tenant-aware, deny by default, and separate roles from resource-scoped permissions. Do not trust tenant IDs or roles supplied by an untrusted browser. A later ADR must establish threat model, identity provider compatibility, and audit requirements.

## Local development

Follow the root [README](../../README.md): copy `.env.example`, start PostgreSQL with Compose, run the API from `apps/api`, and run the web workspace from the repository root. Tests and checks do not need a database. GitHub Actions runs the same API tests/lint and frontend lint/typecheck checks.

## Security and operations

Secrets belong in local ignored environment files or a deployment secret manager. Compose binds PostgreSQL to loopback and uses a clearly development-only example password. Production requires externally managed secrets, TLS and deployment-specific network controls, backups, audit logging, monitoring, and an explicit authentication configuration; this repository does not provide production deployment hardening.

## Open architectural decisions

- Which OIDC provider/protocol profile and session architecture meet self-hosting and enterprise requirements?
- Which tenant partitioning model and PostgreSQL row-level security policy should be used?
- Which OSCAL versions and artifact types are first-class, and which Trestle operations should be wrapped?
- How should domain entities and JSONB artifacts be versioned and migrated?
- What audit event schema, retention, and tamper-resistance requirements apply?
- When should evidence storage be introduced, and which S3-compatible API/features are required?
- Which background job delivery and retry semantics are required before introducing a queue?
