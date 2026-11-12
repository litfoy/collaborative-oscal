# ADR 0010: Authorized catalog import adapter

## Status

Accepted

## Context

The catalog importer was available only to trusted application callers and the CLI.
It deduplicates canonical content within an explicitly selected logical catalog;
without a target it creates a new catalog, even if an identical document exists
elsewhere. Catalog revisions are immutable and existing references are revision-pinned.

## Decision

Expose the existing service through tenant-scoped JSON-only HTTP endpoints requiring
`catalog:import`. The browser sends the original file bytes through the same-origin,
allowlisted BFF. The BFF caps uploads at 100 MiB, the maximum configurable API
limit; the API enforces `CATALOG_IMPORT_MAX_INPUT_BYTES` while reading the body.
Next.js proxy body cloning uses the same 100 MiB ceiling to avoid truncating uploads.
Deployment proxies must allow the configured size and sufficient time for validation.
The browser preview is advisory; the OSCAL package remains authoritative.

The user explicitly chooses a new catalog or a target catalog. A duplicate in the
selected catalog returns the existing revision; no automatic identity matching or
reference migration is performed. A network failure can leave the import outcome
unknown, so users should check the catalog list before retrying.

## Consequences

No separate parsing, persistence, or revision pipeline is introduced. Users must
choose the correct logical target, and new-catalog retries cannot be automatically
deduplicated across catalogs. Large imports are synchronous and subject to the
BFF timeout and deployment limits.
