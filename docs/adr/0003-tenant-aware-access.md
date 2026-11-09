# ADR 0003: Require tenant-aware authorization at data boundaries

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The platform is intended to support multiple organizations and tenants. Missing a tenant scope in a service or data query can expose one organization's data to another.

## Decision

Treat tenant identity as trusted request context established after authentication and carry it explicitly into application services and persistence operations. Enforce authorization and tenant scope at service/data boundaries. Consider PostgreSQL row-level security as defense in depth; do not rely on it as the sole authorization mechanism.

## Consequences

Tenant-owned records and repository interfaces carry explicit tenant scope, and
composite foreign keys reject cross-tenant associations. Tenant IDs must still come
from a verified OIDC principal and active database membership before a tenant-scoped
HTTP operation. The API now provides a reusable tenant-context dependency and
centralized permission evaluation; no tenant-scoped GRC HTTP routes are exposed yet.
PostgreSQL row-level security remains deferred until the context and policy lifecycle
can be tested end to end.
