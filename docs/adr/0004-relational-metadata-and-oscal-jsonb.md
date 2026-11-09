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
specific revision, so they can repeat across catalogs and revisions. Future editing,
import, full schema validation, and Profile/Mapping models must use the OSCAL adapter
boundary and must not treat projections as authoritative.

The digest is deterministic for the JSON values handled here, but it does not claim
RFC 8785 number canonicalization. Full OSCAL validation and supported-version policy
remain future work.
