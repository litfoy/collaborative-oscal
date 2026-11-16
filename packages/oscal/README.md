# OSCAL boundary

This installable package owns OSCAL-specific document handling independently of
the API and domain model. It provides deterministic JSON digests, extraction of
Catalog UUID/version metadata, rebuildable group/control index projections,
secure JSON/YAML parsing, and Catalog/Profile validation for OSCAL 1.0.0–1.0.6,
1.1.0–1.1.3, and 1.2.0–1.2.3, plus Control Mapping validation for OSCAL 1.2.0–
1.2.3. A shared version registry selects the validation path by document type and
declared version. Compliance Trestle 5.2.0 models validate Catalog/Profile
1.1.3, 1.2.0, and 1.2.1, Mapping 1.2.0 and 1.2.1, and compatible
Component Definition/SSP 1.2.1 documents. Other supported versions use their
bundled official NIST JSON Schemas.

Newly authored compatible Profiles, Mapping collections, Component Definitions,
and SSPs default to OSCAL 1.2.1. Their corresponding Trestle-generated model is
the canonical in-memory document representation; the serialized output is
independently checked against the matching official NIST schema and application
integrity checks. Component Definitions and SSPs retain 1.2.3 when required
component types cannot be represented in 1.2.1. Existing editable documents retain
their declared version during ordinary edits.

Catalog import/export, immutable SSP versions, and Component Definition adoption
snapshots preserve their stored source documents and are never reserialized
through Trestle. Parsing, model validation, serialization, official-schema
validation, application integrity checks, and successful cross-document
resolution are distinct guarantees. Catalog projection checks do not claim
exhaustive NIST Metaschema semantic validation, and Profile validation does not
resolve imports. See [Catalog import](../../docs/catalog-import.md) for schema
provenance, parser restrictions, and known validation limitations.
[Control Mapping](../../docs/control-mappings.md) documents the mapping schema
versions, revision-pinned references, and export limitations.

Future Assessment Plans, Assessment Results, and POA&M implementations must use
generated Trestle models from the beginning wherever version-compatible.
Persistence and tenant handling remain outside this package.
