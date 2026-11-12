# ADR 0009: Revision-safe control implementation register

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

Catalog revisions contain normative OSCAL documents; a Profile pins one revision
and selects explicit control IDs. Profiles are editable and are not resolved
catalogs. An OSCAL control ID can recur with different content in later revisions.
The existing organization and tenant membership records are available, but systems,
assessments, evidence storage and audit logging are not implemented.

## Decision

- Store each implementation under its own UUID, in either tenant scope or an
  existing organization in that tenant. Multiple records may address the same
  requirement and scope. No system identity or scope framework is invented.
- Store the original `(tenant, catalog, revision, OSCAL control ID)` and optional
  originating Profile on the implementation. A Profile association is accepted
  only if that exact revision and control are selected at creation. Subsequent
  Profile edits do not delete, change, or detach records. Composite foreign keys
  enforce same-tenant source, organization, Profile and control relationships.
  Control index rows referenced by implementations cannot be deleted; index
  rebuilding must preserve those keys rather than delete and recreate them.
- Protect the source content and identity of referenced draft revisions as well
  as published revisions. The creation transaction locks the revision before
  validation; a database trigger rejects source-content changes once referenced.
  The existing published-revision immutability rule continues to apply.
- Store descriptions, reported status, and bounded textual evidence references on
  the implementation. The statuses are `not_started`, `in_progress`, `implemented`,
  and `not_applicable`. None is an assessment conclusion. References are opaque
  strings, not uploads, validated URLs, or evidence objects.
- Store accountable, responsible, and participant assignments separately. A person
  must be an active tenant member when assigned; role labels can also stand alone.
  Existing assignments survive membership deactivation and can be removed. The
  implementation stores creation and last-modification actors and timestamps;
  assignment history and an audit log are not implemented.
- Reuse `catalog:read` for register reads and `catalog:write` for changes, as for
  Profiles. Authorization is tenant-wide: organizations are organizational scope
  labels, not independent authorization boundaries. Tenant readers can see active
  member display names and organization names for assignment. No identity data is
  sourced from browser-supplied roles or token claims.
- A new revision or Profile creates no implementation association and implies no
  semantic equivalence, migration or assessment validity. Future reviewed mappings
  can add separately dated, attributed implementation-to-definition associations;
  they must retain this original reference and not overwrite past assessments.
  Future evidence and assessments should reference the implementation UUID and
  independently retain their exact assessed revision, control and scope.

## OSCAL alignment

The register is an internal operational model, not an OSCAL SSP. OSCAL's
[SSP model](https://pages.nist.gov/OSCAL/learn/concepts/layer/implementation/ssp/)
describes control implementation, responsible roles and system scope. OSCAL
[Assessment Results](https://pages.nist.gov/OSCAL/learn/concepts/layer/assessment/assessment-results/)
separately record assessments and findings. Future SSP/assessment/POA&M
interoperability requires explicit mapping, including party and role identities,
and must not infer validity from the implementation status.

## API and limitations

`GET/POST /api/v1/tenants/{tenant_id}/implementations` lists and creates records;
the list supports `profile_id`, `organization_id`, `tenant_scope`, `limit` and
`offset`. `GET/PUT .../implementations/{id}` retrieves or replaces operational
information and assignments; `GET .../implementations/{id}/control` returns its
original read-only control. `GET .../implementation-options` returns tenant
organizations and active members for assignment. The Profile workspace exposes
records including those whose controls are no longer selected.

There is no implementation deletion, revision remapping, assessment model, file
storage, system scope, organization-specific RBAC, or assignment history. PUT
replaces the full editable state and currently uses last-writer-wins semantics;
optimistic concurrency and durable audit events are future work. There is no
cross-Profile association UI; records without a Profile remain accessible via the
tenant/scope API.
