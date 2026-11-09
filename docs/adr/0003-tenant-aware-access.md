# ADR 0003: Require tenant-aware authorization at data boundaries

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The platform is intended to support multiple organizations and tenants. Missing a tenant scope in a service or data query can expose one organization's data to another.

## Decision

Treat tenant identity as trusted request context established after authentication and carry it explicitly into application services and persistence operations. Enforce authorization and tenant scope at service/data boundaries. Consider PostgreSQL row-level security as defense in depth; do not rely on it as the sole authorization mechanism.

## Consequences

Future tenant-owned entities and repository interfaces must make tenant scope explicit and test cross-tenant denial. The tenant partitioning strategy, identity integration, and database policies remain undecided. This foundation implements none of them.
