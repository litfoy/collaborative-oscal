# OSCAL boundary

This installable package owns OSCAL-specific document handling independently of the
API and domain model. It provides deterministic JSON digests, extraction of catalog
UUID/version metadata, rebuildable group/control index projections, secure JSON/YAML
parsing, and Catalog/Profile validation for OSCAL 1.0.0–1.0.6, 1.1.0–1.1.3,
and 1.2.0–1.2.3, plus Control Mapping validation for OSCAL 1.2.0–1.2.3.
A shared version registry selects the bundled official NIST JSON
Schema for 1.0.0–1.0.6, 1.1.0–1.1.2, 1.2.2, and 1.2.3;
compliance-trestle 5.2.0 models validate Catalog/Profile 1.1.3, 1.2.0, and 1.2.1
and Mapping 1.2.0 and 1.2.1. Newly generated Profiles and Control Mapping
collections default to 1.2.3. Validation returns structured errors and warnings and
never modifies the source document.

The bundled 1.2.2 and 1.2.3 schema validation is a temporary compatibility bridge;
replace it with compliance-trestle validation when an approved Trestle release
supports those OSCAL versions.

Trestle models are used for validation only; their serialized output is never used
to replace source documents. JSON Schema/Trestle model validation and Catalog
projection checks do not claim exhaustive NIST Metaschema semantic validation, and
Profile validation does not resolve imports. See
[Catalog import](../../docs/catalog-import.md) for schema provenance, parser
restrictions, and known validation limitations.
[Control Mapping](../../docs/control-mappings.md) documents the mapping schema
versions, revision-pinned references, and export limitations.
Persistence and tenant handling remain outside this package.
