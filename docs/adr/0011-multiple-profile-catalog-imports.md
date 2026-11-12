# ADR 0011: Revision-pinned Profile imports

- **Status:** Accepted
- **Date:** 2026-11-12
- **Supersedes:** the single-source decision in ADR 0008

## Decision

A tenant-owned Profile has ordered, independently identified catalog imports. The
OSCAL Profile JSONB document is authoritative for selections; `profile_imports`
records import identity, order, exact tenant-owned catalog revision and active
state. Both are changed in one transaction. Repeated imports of the same
revision are allowed. A selection is identified by its import, revision and
original OSCAL control ID, never by control ID alone.

The Alembic migration creates one import per existing Profile, preserves the
document and backfills implementation provenance without recreating records or
responsibilities. It aborts on inconsistent sources. Removed imports remain
inactive, and their source revisions remain protected from normative mutation.
Implementations retain their original Profile, catalog, revision, control and
import references even after deselection or removal. Import source identity
cannot be changed in place. Downgrade refuses Profiles with multiple or inactive
imports rather than discarding data.

Profile writes use the existing tenant `catalog:write` permission; reads use
`catalog:read`. Every source and selection is validated within that tenant.
The existing single-source request form remains available for single-import
Profiles; it cannot overwrite a multi-import Profile. Profile document UUIDs
change on saved content changes; internal Profile and import UUIDs do not.
The legacy top-level source and control fields in responses describe only the
first import; clients that support multi-import Profiles must use `imports`.

Each export preserves the declared Profile OSCAL version and validates through
compliance-trestle for versions through 1.2.1 or the matching bundled official NIST
JSON Schema for 1.2.2 and 1.2.3. New Profiles default to 1.2.3. Imported Catalog
versions remain independent of the Profile version. See
[ADR 0012](0012-oscal-versioned-schemas.md) for the version registry, schema
provenance, and dependency boundary. Selections are explicit; selecting a parent
does not implicitly include its descendants.

## Limitations

The generated root-relative `href` values refer to authenticated API revision
export endpoints. They need the API origin and authorized access; a downloaded
file or a browser BFF origin alone does not make them portable. Profile schema
validation is not Profile resolution. In particular, identical control IDs from
different sources remain separate and may prevent a resolver from producing a
valid Catalog. No automatic mapping, renaming or deduplication is performed.

The implementation register remains an internal operational model, not an
OSCAL SSP. It does not provide assessment history, system scope or assignment
audit history. Profile updates remain last-writer-wins and do not provide full
Profile revision history.
