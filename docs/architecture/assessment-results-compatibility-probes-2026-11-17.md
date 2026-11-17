# Assessment Results Compatibility Probes (2026-11-17)

## Scope

Read-only runtime verification for OSCAL Assessment Results (AR) compatibility using:

- Compliance Trestle `5.2.0`
- OSCAL `1.2.1`
- Official schema asset: `oscal_assessment-results_schema.json`

No repository implementation, dependency, migration, or database changes were made.

## Environment and schema provenance

- Locked execution: `uv run --locked`
- Trestle version probe: `5.2.0`
- Official schema URL:
  - `https://github.com/usnistgov/OSCAL/releases/download/v1.2.1/oscal_assessment-results_schema.json`
- Schema checksum:
  - `sha256: 4f9e277a177adbcca9527612ce450a33dc6096773fa229d413d801d196c61985`
  - Size: `152147` bytes

## Probe execution summary

All probes were executed with representative in-memory AR payloads and validated through:

1. Trestle model validation + serialization (`trestle.oscal.assessment_results.Model`)
2. OSCAL schema validation using the repository's unicode-safe validator extension (`_OSCAL_DRAFT7_VALIDATOR`)

### Probe A - Minimal AR document

- Result: `PASS` (Trestle), `PASS` (schema)
- Required root and minimal result assembly validated.

### Probe B - `import-ap` reference

- Result: `PASS` (Trestle), `PASS` (schema)
- URI-form `import-ap.href` accepted.

### Probe C - Reviewed controls and objectives

- Result: `PASS` (Trestle), `PASS` (schema)
- `control-selections` and `control-objective-selections` accepted.

### Probe D - Observation methods, subjects, collection timestamp

- Result: `PASS` (Trestle), `PASS` (schema)
- Observation with methods `EXAMINE`, `INTERVIEW`, `TEST`, subject, and `collected` accepted.

#### D-negative - invalid method literal (`SCAN`)

- Result: `PASS` (Trestle), `PASS` (schema)
- Meaning: schema/model currently allow arbitrary string methods; strict method policy requires app-level validation.

### Probe E - Relevant evidence and back-matter resource linkage

- Result: `PASS` (Trestle), `PASS` (schema)
- Observation `relevant-evidence` and `back-matter.resources` representation validated.

### Probe F - Finding target, target status, related observations

- Result: `PASS` (Trestle), `PASS` (schema)
- `target.type=statement-id`, `target-id`, and `status.state` accepted.

#### F-negative - invalid target type (`control-id`)

- Result: `FAIL` (Trestle), `FAIL` (schema)
- Exact semantic constraint confirmed: allowed values are only `statement-id` and `objective-id`.

### Probe G - Explicit origin and related task references

- Result: `PASS` (Trestle), `PASS` (schema)
- `origins.actors` and `origins.related-tasks` accepted for observations/findings.

### Probe H - Representative risk structure + objective-id finding target

- Result: `PASS` (Trestle), `PASS` (schema)
- Risk assembly (`uuid/title/description/statement/status`) accepted.
- `target.type=objective-id` accepted.

## Additional targeted checks

### Related observation UUID referential integrity

- Payload with finding referencing a non-existent `related-observations[].observation-uuid`:
  - Result: `PASS` (Trestle), `PASS` (schema)
- Implication: referential integrity must be enforced at application layer.

### `metadata.version` non-empty requirement

- Payload with `metadata.version=""`:
  - Result: `FAIL` (Trestle), `FAIL` (schema)
- Confirms non-empty version semantics are technically enforced.

### Validator behavior note

- Plain `jsonschema.Draft7Validator` on the official schema can fail on Python regex `\p{...}` escapes.
- The repository's `_OSCAL_DRAFT7_VALIDATOR` (using the `regex` package) validates correctly and must be reused for AR schema checks.

## Catalog statement-id feasibility

Statement identifiers were extracted from repository examples to verify valid finding targets are available without fabrication:

- `examples/catalogs/Grundschutz++-resolved_catalog.json`
  - `1000` statement IDs (sample: `GC.1.1_stm`, `GC.1.2_stm`, ...)
- `examples/catalogs/sample-security-practices.json`
  - `6` statement IDs (sample: `ac-1_smt`, `ac-1.1_smt`, ...)
- `examples/catalogs/sample-data-handling.json`
  - `2` statement IDs (sample: `dh-1_smt`, `dh-2_smt`)

## Pinned AP local objective target feasibility

Existing AP integration tests demonstrate local objective identifiers in pinned-plan workflows, supporting AR `objective-id` targeting:

- `apps/api/tests/test_assessment_plans.py:178`
- `apps/api/tests/test_assessment_plans.py:197`
- `apps/api/tests/test_assessment_plans.py:206`

## Architecture corrections from probe evidence

1. Use the repository unicode-safe Draft7 validator extension for AR schema validation.
2. Enforce finding target semantics (`statement-id` or `objective-id`) at API/domain level with historical context resolution.
3. Add app-level policy if method set should be constrained to `EXAMINE|INTERVIEW|TEST` for milestone UX.
4. Add app-level referential integrity checks for related observations and historical target resolution.
5. Keep AP-style persistence simplification: AR document JSONB working state + immutable versions (no extra working-copy table unless required).
6. Reuse existing authorization conventions; no AR-specific permission taxonomy by default.

## Remaining blockers before implementation

1. Add official AR schema asset to `packages/oscal` schema bundle with pinned provenance/checksum.
2. Extend `packages/oscal` version/model registry to include AR support.
3. Implement AR-specific validator module mirroring AP layered diagnostics.
4. Implement application integrity checks for pinned historical references and tenant-safe linking.

