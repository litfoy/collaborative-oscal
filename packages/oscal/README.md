# OSCAL boundary

This installable package owns OSCAL-specific document handling independently of the
API and domain model. It currently provides deterministic JSON digests, extraction
of catalog UUID/version metadata, and rebuildable group/control index projections.
These helpers do not implement full OSCAL parsing or schema validation and do not
modify the source document.

Future import/export, version validation, and optional IBM compliance-trestle
integration belong behind this boundary. No Trestle integration or supported-version
policy is implemented.
