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

## Profile Builder presentation

- Replace manual ID entry with a dedicated editing workspace and structured
  overview. Duplicate uses the existing create operation and retains the original
  pinned revision; it does not select the latest revision.
- Provide a read-only `profile-browser` projection of a revision through the same
  tenant-authorized catalog service. Hierarchy and text/property extraction remain
  in `packages/oscal`; no new database representation is maintained. The browser
  indexes this compact projection once, filters locally, paginates requirement
  results (50 per page), and requests full control details only when opened.
  Navigation loads 100 siblings at a time; grouped selection summaries render
  their entries only when expanded, also in batches of 100.
- Filters reflect actual namespaced properties, including properties on parts and
  parameters. BSI `modal_verb`, `sec_level`, `effort_level`, `tags`, and
  `target_object_categories` receive readable labels, without requiring these
  properties on other catalogs. High-cardinality properties remain readable in
  details rather than generating impractical filter lists.
- Checkboxes select exactly one control. Descendants require their own checkbox
  or an explicitly labelled bulk action. Persist the resulting unique IDs in
  `include-controls[].with-ids`; omitted `with-child-controls` has OSCAL's `no`
  default. Never set `with-child-controls: yes` implicitly. Bulk selection applies
  to every filtered match, including matches on other result pages.
- Store optional profile purpose in OSCAL metadata `remarks`, not a new relational
  column. Existing clients omitting description on update preserve those remarks.
- Support up to 10,000 explicit IDs per profile; the BFF retains a bounded 3 MiB
  mutation body limit to accommodate this selection size. Empty selections cannot
  be saved. Source revision IDs are immutable on update.
- Protect dirty drafts on exit and browser unload, retain them on failed writes,
  and expose export only for the last saved state. Selecting requirements defines
  scope and is never represented as a compliance assessment.
