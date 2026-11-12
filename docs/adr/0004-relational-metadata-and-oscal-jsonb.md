# ADR 0004: Store relational ownership and OSCAL revision snapshots

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Catalog content is versioned OSCAL data with nested structures that evolve by OSCAL
revision. Tenant ownership, catalog identity, revision lifecycle, and common query
paths still need relational integrity. Flattening the full OSCAL catalog into
application tables would lose extensibility and couple domain entities to a
serialization model.

## Decision

Use PostgreSQL relational tables for tenants, organizations, logical catalogs,
revision metadata, and tenant/revision-scoped group and control query indexes. Store
the complete OSCAL JSON document as authoritative JSONB on each catalog revision.
Treat the indexes as rebuildable projections, not the source of OSCAL content.
Compute a deterministic SHA-256 digest over compact UTF-8 JSON with sorted object
keys, preserved Unicode, and non-finite values disallowed.

Give each logical catalog an application-generated UUID independent of any OSCAL
document. Give each stored catalog revision a separate UUID and unique sequential
revision number within its tenant/catalog. Preserve the document UUID and metadata
from OSCAL content; do not generate or replace them during storage or projection.
Draft revisions may transition to published only with a publication timestamp;
published revisions are immutable at the database boundary.

## Consequences

Unknown OSCAL fields and nested content remain preserved in JSONB while relational
queries use indexed fields and paths. Control identifiers are unique only within a
specific revision, so they can repeat across catalogs and revisions. Import and
editing must use the OSCAL adapter boundary and must not treat projections as
authoritative. Full NIST Metaschema semantic validation remains future work.

The digest is deterministic for the JSON values handled here, but it does not claim
RFC 8785 number canonicalization. Catalog and Profile validation use compliance-trestle
models for OSCAL 1.1.3, 1.2.0, and 1.2.1 and bundled NIST JSON Schemas for
1.0.0–1.0.6, 1.1.0–1.1.2, 1.2.2, and 1.2.3;
Catalog documents remain authoritative and are not rewritten through a validation
model. See [ADR 0012](0012-oscal-versioned-schemas.md) and the
[Catalog import guide](../catalog-import.md) for the validation boundary and
limitations.
