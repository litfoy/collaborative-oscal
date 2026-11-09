# Domain boundary

The first GRC domain entities and invariants live in `apps/api/app/domain`, with
application operations in `apps/api/app/application` and repository protocols in
`apps/api/app/domain/repositories.py`. This logical boundary remains independent of
FastAPI, SQLAlchemy, and OSCAL serialization models. The `packages/domain` directory
is documentation for a future separately packaged library, not an installed Python
package.

Current internal entities are Tenant, Organization, Catalog, and CatalogRevision,
with domain-level organization hierarchy validation. Persistence and query
projections are in separate API modules. No tenant-scoped REST endpoints,
authentication, full catalog workflows, profiles, mappings, risks, assessments,
evidence, automation, or AI governance are implemented.
