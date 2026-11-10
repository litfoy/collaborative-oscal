# ADR 0008: Persist basic OSCAL Profiles separately from Catalog revisions

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

Users need to define control selections from imported catalogs without mutating or
copying those immutable catalog documents. Catalog revisions already provide stable
tenant-scoped identities and indexed OSCAL control IDs.

## Decision

- Store each Profile as its own tenant-owned JSONB document, with relational
  references to one source catalog and exact revision. A composite foreign key
  enforces that the source revision belongs to that catalog and tenant.
- Generate OSCAL `imports` with a stable revision export URL and
  `include-controls` selections by OSCAL control ID. Validate that every selected
  ID exists in the exact referenced revision before create or update.
- Keep OSCAL Profile construction and model validation within `packages/oscal`.
  Support the repository's OSCAL 1.1.3 and 1.2.1 compatibility boundary.
- Require the existing tenant-scoped `catalog:write` permission for create and
  update; reads and exports require `catalog:read`.
- Do not resolve Profiles or copy Catalog content into them. The browser UI supports
  basic Profile creation and editing through the API.

## Consequences

- Profile updates modify only their own JSONB documents; catalog revisions remain
  authoritative and unchanged.
- The revision export endpoint gives Profile imports a stable API resource to
  resolve, subject to the same tenant authorization as Catalog browsing.
- Full OSCAL Profile resolution and cross-catalog import composition remain future
  application services.
