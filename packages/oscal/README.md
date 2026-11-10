# OSCAL boundary

This installable package owns OSCAL-specific document handling independently of the
API and domain model. It provides deterministic JSON digests, extraction of catalog
UUID/version metadata, rebuildable group/control index projections, secure JSON/YAML
parsing, and Catalog validation for OSCAL 1.1.3 and 1.2.1. OSCAL 1.1.3 is checked
against the bundled NIST schema, and OSCAL 1.2.1 uses compliance-trestle model
validation. Validation returns structured errors and warnings and never modifies
the source document.

The importer uses Trestle's Pydantic OSCAL model. This does not claim exhaustive NIST
Metaschema semantic validation; see [Catalog import](../../docs/catalog-import.md)
for the compatibility policy, parser restrictions, and known validation limitations.
Persistence and tenant handling remain outside this package.
