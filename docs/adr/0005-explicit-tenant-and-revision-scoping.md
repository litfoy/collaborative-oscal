# ADR 0005: Enforce tenant and revision scope in data relationships

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The application has no authentication yet, but its initial persistence model must
not permit tenant-owned records to be associated across tenants. Organizations are
hierarchical, and catalog query projections must identify the exact source revision.
Future Profile and Control Mapping domains will depend on stable, tenant-scoped
catalog identities.

## Decision

Every tenant-owned row stores `tenant_id`. Application services and repository
interfaces require explicit tenant scope for tenant-specific lookups and listings.
Composite foreign keys enforce same-tenant organization parentage, catalog-to-revision
ownership, and same-tenant/same-revision group/control index relationships.
Organization parent-chain validation belongs to the domain layer.

Tenant context is to be established from a future authenticated principal, then
passed explicitly through services and repositories. Client-supplied tenant IDs are
not trusted without authorization. PostgreSQL row-level security is deferred until
tenant context can be installed and removed transactionally and policies can be
tested; it is defense in depth, not a substitute for application checks.

Profiles and Control Mappings are future domain boundaries. They may refer to a
catalog revision and its control index, but neither will be folded into catalog
content or inferred from a client-controlled tenant identifier.

## Consequences

Database constraints reject invalid cross-tenant associations even if a future
service has a bug, while tenant-scoped repository queries prevent cross-tenant
retrieval through normal application operations. Authentication, RBAC, audit
requirements, stronger tenant partitioning, and RLS policies remain unimplemented.
