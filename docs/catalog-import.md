# OSCAL Catalog import

The internal `CatalogImportService` imports raw JSON or YAML bytes into the existing
tenant-scoped catalog repository. Before the browser integration there was no HTTP
import endpoint: the CLI and trusted application callers were the only adapters.
The service does not discover logical catalog identity automatically: callers must
explicitly select a target to create a revision or detect an existing document.
Without a target, even an identical document creates a separate logical catalog.

The HTTP adapter accepts the unchanged UTF-8 JSON document as `application/json`
at `POST /api/v1/tenants/{tenant_id}/catalogs/import`, or at
`POST /api/v1/tenants/{tenant_id}/catalogs/{catalog_id}/import` for an explicit
target. Both require `catalog:import`. The response identifies the catalog and
revision and reports whether a revision was created; identical content in the
selected catalog returns the existing revision. The configured
`CATALOG_IMPORT_MAX_INPUT_BYTES` limit applies. Existing profiles and implementation
references remain pinned to their original revisions.

## Architecture and processing

```mermaid
sequenceDiagram
    participant Caller as Trusted application caller
    participant Service as CatalogImportService
    participant OSCAL as packages/oscal
    participant UOW as SQLAlchemy UnitOfWork
    participant DB as PostgreSQL
    Caller->>Service: import_catalog(tenant, bytes, format, metadata, target?)
    Service->>OSCAL: Parse safely and validate Catalog model
    OSCAL-->>Service: Structured report + validated JSON object
    Service->>Service: Calculate canonical digest and prepare projections
    Service->>UOW: Begin transaction
    UOW->>DB: Verify tenant and target catalog scope
    UOW->>DB: Find digest, lock catalog, recheck digest
    UOW->>DB: Insert catalog (if new), revision, groups, controls
    UOW->>DB: Commit all records atomically
    UOW-->>Service: Commit result
    Service-->>Caller: Catalog, revision, count, created flag
```

Parsing and validation happen before opening a database transaction. Invalid input
raises `CatalogImportValidationError` with a reusable `CatalogValidationResult`;
invalid content is never persisted. A valid import verifies the tenant and
tenant-scoped target catalog, creates a logical catalog if no target was given,
then writes the catalog, draft revision, and derived group/control projections in
one unit of work. Database errors roll back the whole transaction.

The importer reuses `canonical_json_sha256` from the OSCAL package. JSON and YAML
documents with the same parsed values therefore have the same digest. Digest
lookups are scoped to one logical catalog. A partial unique database index on imported revisions and a lock
on the logical catalog serialize same-catalog imports; a second digest lookup after
the lock makes identical concurrent imports return the existing revision. A
different digest creates the next draft revision. Published revisions are never
updated; an identical published revision is returned as-is.

Group and control indexes are rebuilt from the stored OSCAL object with the existing
projection helper. Hierarchy and source order are retained, and identifiers can
repeat in separate catalogs. Indexes are tied to the exact tenant and revision.
The original JSON/YAML semantic content is preserved in JSONB; YAML comments and
formatting are not retained.

The structured validation result includes `valid`, document type, declared OSCAL
version, validator name/version, validation schema version, errors, and warnings.
Errors have a stable code, safe human-readable message, optional JSON Pointer, and
optional diagnostic code. Parser errors do not include imported content. The
default input limit is 100 MiB and the default maximum nesting depth is 64; both can
be overridden on the internal service. YAML uses `SafeLoader`, rejects duplicate
mapping keys and aliases, permits one document only, and does not resolve dates to
Python objects. JSON duplicate object keys and non-finite numbers are rejected.
Both formats require UTF-8. No URLs or references are fetched.

## Compatibility

| Area | Supported behavior |
|---|---|
| compliance-trestle | `5.2.0` (dependency range `>=5.2,<5.3`) |
| Python | Trestle declares `>=3.11`; this repository targets Python 3.12–3.13 |
| OSCAL versions accepted by Catalog import | `1.0.0`–`1.0.6`, `1.1.0`–`1.1.3`, `1.2.0`–`1.2.3` |
| OSCAL versions accepted by Profile generation/export | `1.0.0`–`1.0.6`, `1.1.0`–`1.1.3`, `1.2.0`–`1.2.3` |
| Default for newly generated Profiles | `1.2.3` |
| OSCAL documents | Catalog JSON model only |
| Input formats | JSON and YAML; optional safe first-character auto-detection |
| Version-specific validation | compliance-trestle 5.2.0 models for 1.1.3, 1.2.0, and 1.2.1; bundled official NIST JSON Schema Draft 7 for the other supported versions |
| Additional Catalog checks | Existing group/control projection and duplicate control-ID rejection |

### Official schema provenance

The schemas are bundled locally; application validation makes no runtime network
requests. Each checked-in schema is sourced from the matching OSCAL release's
`oscal_catalog_schema.json` or `oscal_profile_schema.json` asset. The table gives
SHA-256 for the exact checked-in bytes.

| OSCAL release | Catalog schema SHA-256 | Profile schema SHA-256 |
|---|---|---|
| [1.0.0](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.0) | `622b96ca950656d56ea184b080929a6a079d49db50011d7f2c362b268b962d42` | `4efd7cc88e8eb77896574dc23404df20ae623b8c2c0b11927559f707fe0ca33a` |
| [1.0.1](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.1) | `622b96ca950656d56ea184b080929a6a079d49db50011d7f2c362b268b962d42` | `4efd7cc88e8eb77896574dc23404df20ae623b8c2c0b11927559f707fe0ca33a` |
| [1.0.2](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.2) | `34e60e908a31dc40f30308a90d1a5727bc709b2c7149ea76d3232268fbad9759` | `9c1a2830c32f0d2dc2bd10f2f4667751fe718f7425d6c01a2075728ac3fa1531` |
| [1.0.3](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.3) | `42ebb82bb6c4b8ee18f7f29f479997f60d07a0f0d89db6c4947a9d1036b8a78a` | `b954d19effee74fb457bc04393d0a2c23fc80625e746205e1f571b8fb9858960` |
| [1.0.4](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.4) | `ff3f66f879340ac3c35e03561d4b6ce2948aad7b87f993b6d4e647141bf848b3` | `013288f650344a42574ad635c70415d4fa77f6f2f53a81b38809c78b0fc968c9` |
| [1.0.5](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.5) | `2a0ea3628809d363d796dcccac82a43e56e397291f6ab904d4df6c44eaf251a0` | `27d8c13b313cc2a79f3fe81b01f5953daa5a15c29dfa01fb34f9e484a97a67e2` |
| [1.0.6](https://github.com/usnistgov/OSCAL/releases/tag/v1.0.6) | `38ec593fbc020d164d85db67e4f6b5532788f5e4f26de33e6448b3abe7610a2b` | `0fb18c4c00f8509dbec8847a7d1b7479ddb72b32ddb2f987619d7a179eac8d64` |
| [1.1.0](https://github.com/usnistgov/OSCAL/releases/tag/v1.1.0) | `936c53978eb47880dfa8b471640ae09b111b38d837686022ef7db07e26fa629d` | `e40698f88744d07ff4d06512d7359b18c10bf15ca97de6ce0b61d53bd82d19af` |
| [1.1.1](https://github.com/usnistgov/OSCAL/releases/tag/v1.1.1) | `90fb059843026fcc99d38dfd1102ea4bc12d0f43a443ba79aa7d6ce3df6a9100` | `067c7da65da2a90017d9f42a81d4a9d73d1dba56990e2a0bf86c438dc167e241` |
| [1.1.2](https://github.com/usnistgov/OSCAL/releases/tag/v1.1.2) | `5b069afa4f4ecc38d59914dab56098566d4247d3578a2123c030c80d36fc5104` | `c910ea1a852e9d4ccfb7f6a8d0898b0cd4f137e48f88886412a083c8d87d540a` |
| [1.2.2](https://github.com/usnistgov/OSCAL/releases/tag/v1.2.2) | `fdc559f5dff6848b1ebbe1898a69cc08263479f7c796e2f056412059e7489d0c` | `04329bd68032f48825f712f79576b3fd00e129e59d3597beb56ed72c17277f66` |
| [1.2.3](https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3) | `ab95836e9e8dfebf6fde80007f6cc76fa3192f595d427c751a3f3923c3f474fc2` | `7c5ff5a92683b6a80ce6a3474dea04e0ea8680a4ecb60702ffa08ebfc677e6cb` |

The 1.2.2 and 1.2.3 schemas are version-specific, not aliases. Comparing the NIST
release assets shows that 1.2.2 corrects JSON integer datatypes (the Catalog schema
changes only its version identifier from 1.2.1).
For 1.2.3, the Catalog schema changes only its version identifier, while the Profile
schema updates the description of `modify.alters.removes` matching by item name.
These differences are why the declared version selects its own schema for these
newer versions rather than falling back to the latest one.

NIST's 1.0.1 release assets have the same bytes and `$id` as 1.0.0; the 1.0.5
assets retain a 1.0.4 `$id`. They are kept exactly as published and selected by
the release version, not by `$id`. In particular, the official 1.0.5 Catalog
schema has stricter property and link enumerations than 1.0.4; validation uses
those constraints rather than silently substituting another schema.

### Parsing and dependency boundary

The importer validates OSCAL 1.1.3, 1.2.0, and 1.2.1 Catalogs with compliance-trestle
5.2.0's generated 1.2.1 model. OSCAL 1.0.0–1.0.6, 1.1.0–1.1.2, 1.2.2,
and 1.2.3 Catalogs use their corresponding official NIST schemas. Profile validation
uses the same version split. The BSI 1.1.3 Catalog and generated Profiles through
1.2.1 are covered by application tests. Trestle models are used only for validation:
the parsed input dictionary is returned and persisted without rewriting
`metadata.oscal-version`, identifiers, or fields. Catalog `x-` extension keys are
excluded from the validation view; their original values remain in the imported
document and extension-specific constraints are not checked.

Trestle 5.2.0 does not guarantee backward compatibility with all older documents:
for example, its 1.2.1 Profile model rejects the `merge.combine.method` construct
accepted by the official OSCAL 1.0.0 Profile schema. Earlier versions therefore
use their own official schemas rather than the Trestle model.

The 1.2.2 and 1.2.3 schema paths are temporary compatibility bridges. Replace them
with compliance-trestle validation when an approved Trestle release supports those
versions; keep the version-specific compatibility tests and document-preservation
behavior.

The BSI Grundschutz++ fixture declares OSCAL 1.1.3 and passes Trestle model
validation and existing projections. The official NIST SP 800-53 Rev. 5.2.0 Catalog fixture is from
the independent [OSCAL Content release `v1.5.0`](https://github.com/usnistgov/oscal-content/releases/tag/v1.5.0);
its declared OSCAL version is 1.2.2.
The checked-in fixture
[`NIST_SP-800-53_rev5_catalog-min.json`](../apps/api/tests/fixtures/NIST_SP-800-53_rev5_catalog-min.json)
has SHA-256 `d820835aa54aeb2265bdacdf8e678af7530443a59556563df898addf012024cb`.
The smaller local Catalog fixture used for other version cases is self-authored test
data, not NIST content.

Trestle model validation and Catalog/Profile JSON Schema validation are distinct
from comprehensive OSCAL semantic validation. Catalog import also projects groups
and controls and rejects duplicate control identifiers. Validation does not
implement every NIST Metaschema semantic constraint. Profile validation does not
resolve its imports or guarantee that a resolver can compose the referenced
Catalogs. No Trestle CLI or remote schema download is used.

## Provenance and security boundary

Existing catalog columns store source URI, source organization, and license
identifier. Revision columns store the OSCAL document UUID/version, source
document version, canonical checksum, creation/import timestamp, and input format.
The full source metadata including title, publisher and `last-modified` remains in
the authoritative OSCAL content. Imported OSCAL metadata is not rewritten.

`tenant_id` is an explicit application-service argument and every catalog lookup,
duplicate check, and revision write is tenant-scoped. The caller must provide a
tenant identity established by a trusted boundary; the HTTP adapter authenticates
and authorizes the caller before invoking it. Catalog IDs from another tenant are indistinguishable from
missing IDs. Tenant IDs in imported documents are never used. Input parsers do not
instantiate YAML objects, follow paths, or access the network; errors and
diagnostics exclude full document content.

## Local development

Run from `apps/api` after installing the locked dependencies and starting the local
PostgreSQL database. The example uses an explicitly selected tenant ID and is for a
trusted developer/admin process only; it is not an authenticated user interface.

```python
import os
from pathlib import Path
from uuid import UUID

from app.application.catalog_import import CatalogImportService
from app.persistence.database import create_unit_of_work_factory

service = CatalogImportService(create_unit_of_work_factory())
tenant_id = UUID(os.environ["TENANT_ID"])
source = Path("catalog.json")
validation = service.validate_catalog(source.read_bytes(), "json")
if not validation.result.valid:
    for error in validation.result.errors:
        print(error.code, error.path, error.message)
    raise SystemExit(1)

result = service.import_catalog(
    tenant_id,
    source.read_bytes(),
    "json",
    target_catalog_id=None,
)
print(result.catalog.id, result.revision.id, result.control_count)
```

Set `target_catalog_id` to import a new revision into an existing tenant-owned
logical catalog. Without it, each call creates a new logical catalog.

## Local sample data

Catalog import defaults to a 100 MiB input limit for both the API and CLI. It can
be lowered with `CATALOG_IMPORT_MAX_INPUT_BYTES` (bytes, maximum 100 MiB) in the
environment or root `.env`. The browser and BFF enforce the same 100 MiB limit.

Two self-authored OSCAL 1.2.1 catalogs live in `examples/catalogs/`. Import them with `python -m app.cli create-tenant` and `import-catalog` (run from `apps/api`); see [Catalog Explorer](architecture/catalog-explorer.md#local-setup). The CLI uses the same import service and validation as every other caller.
