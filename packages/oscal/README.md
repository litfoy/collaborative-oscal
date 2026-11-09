# OSCAL boundary

This installable package owns OSCAL-specific document handling independently of the
API and domain model. It provides deterministic JSON digests, extraction of catalog
UUID/version metadata, rebuildable group/control index projections, secure JSON/YAML
parsing, and compliance-trestle Catalog model validation for OSCAL 1.2.1. Validation
returns structured errors and warnings and never modifies the source document.

The importer uses Trestle's Pydantic OSCAL model. This does not claim exhaustive NIST
Metaschema semantic validation; see [Catalog import](../../docs/catalog-import.md)
for the compatibility policy, parser restrictions, and known validation limitations.
Persistence and tenant handling remain outside this package.
