# OSCAL Control Mappings

Control Mapping collections describe explicit relationships between normative
controls from immutable catalog revisions. They are independent of Profiles,
Profile selections, implementation records, and assessment status. Creating or
editing a mapping never changes a catalog, selects Profile controls, or asserts
that a requirement has been implemented or fulfilled.

## OSCAL model and supported versions

Exports use the official OSCAL `mapping-collection` root model and default to
OSCAL 1.2.3. Mapping collections support OSCAL 1.2.0 through 1.2.3; OSCAL 1.1.3
is not a Mapping Model version. Mapping validation uses Compliance Trestle 5.2.0
for 1.2.0 and 1.2.1, then the official NIST JSON Schemas for 1.2.2 and 1.2.3.
The 1.2.2 and 1.2.3 schema assets are from the
[OSCAL 1.2.2](https://github.com/usnistgov/OSCAL/releases/tag/v1.2.2) and
[OSCAL 1.2.3](https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3) releases:

| OSCAL schema | SHA-256 |
|---|---|
| 1.2.2 Mapping | `45b4f909f72e17fbe8476e2a7f3d9f64ec42dc26ab2fe2d56c6b44fc57346022` |
| 1.2.3 Mapping | `ed28b68c8e56cc7d39f0c6076a5d7da3e8100fbe25abf5bb731120bd34f8817e` |

These are only the Mapping Model validation paths. Catalogs remain independently
versioned, so a 1.2.3 Mapping collection can refer to an older supported catalog
revision such as an OSCAL 1.1.3 catalog.

## Persistence and identity

`mapping_collections` stores the authoritative OSCAL document as JSONB with a
stable tenant-scoped internal collection ID and relational creator/updater
provenance. `mapping_members` is a transactional lookup and referential-integrity
projection of source and target set members; it stores no normative control
content. Each member is qualified by tenant, catalog, immutable revision, side,
mapping UUID, entry UUID, member type, and the original OSCAL member identifier.
Composite foreign keys reject cross-tenant references and controls absent from
the referenced revision's index.

An OSCAL document UUID is regenerated when its document is revised, and the
document version is incremented. Mapping and mapping-entry UUIDs remain stable
when those identities are retained in an update. Collection JSON and its member
projection are written in one database transaction; the JSON is the sole
authoritative representation of mapping semantics.

Every source and target reference pins one exact catalog revision. References
are never advanced when a new catalog revision appears. Database row locks
serialize mapping creation or removal with revision changes, and a database
trigger rejects normative updates while any mapping member references a
revision. Deleting a mapping collection removes its lookup projection and
releases that protection. The collection currently stores its latest document,
not a revision history of mapping documents.

## Relationships and granularity

The UI supports the official relationship tokens `equal-to`, `equivalent-to`,
`subset-of`, `superset-of`, `intersects-with`, and `no-relationship`, paired with
the official matching rationales `syntactic`, `semantic`, and `functional`.
The manually authored mapping method is `human`; new mappings have draft status.
No confidence score or review state is claimed. `equal-to` and `equivalent-to`
remain distinct. Reverse display changes `subset-of` to `superset-of` and vice
versa; symmetric relationships retain their value. An absent mapping is not a
`no-relationship` assertion, and no transitive mappings are inferred.

Each OSCAL map entry relates source and target sets as a whole. Multiple
controls on either side are preserved without decomposition into pairwise
assertions. The initial API and UI support whole controls only. OSCAL statement
members are retained as a future extension point in the relational projection,
but statement-level selection and validation are not implemented; no statement
IDs are fabricated.

## API, authorization, and export

Tenant-authorized routes create, list, retrieve, update, delete, and export
collections under `/api/v1/tenants/{tenant_id}/mapping-collections`. Related
mappings are looked up by exact catalog revision and control ID. Mapping routes
reuse `catalog:read` and `catalog:write`, and revision identity is always
tenant-scoped. The web application exposes a Control Mappings area and adds
related mapping context to each catalog control's details.

The JSON export references catalog revisions using authenticated application API
URLs. Those references work only where the API and appropriate authorization are
available; the exported collection is not a self-contained portable package.
OSCAL Mapping import is not implemented.

## Verification and limitations

Focused unit tests validate the Trestle 1.2.0/1.2.1 and JSON Schema 1.2.2/1.2.3
paths, unsupported versions, and inverse relationship semantics. PostgreSQL
integration tests cover persisted mapping round trips, same-ID controls in
different catalogs, set cardinality, tenant isolation, export validation, and
revision protection; they require the dedicated `TEST_DATABASE_URL` ending in
`_test`. The migration is not applied automatically to an application database.

For this implementation, the complete API suite reported 184 passed and 42
skipped, including mapping document validation; web type-check and lint passed;
and all 16 BFF route tests passed. The PostgreSQL mapping integration test was
skipped because `TEST_DATABASE_URL` was not configured. The jsdom-based web
component suite could not complete with the available Node 22.8.0 runtime,
which is below the web package's `>=22.13.0` engine requirement and lacks the
API expected by the installed `undici` version.

The first release does not provide Mapping import, statement-level mapping,
automatic mapping, confidence scoring, approval workflows, revision migration,
or standalone export resolution.
