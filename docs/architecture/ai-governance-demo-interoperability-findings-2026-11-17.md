# AI Governance Interoperability Findings (2026-11-17)

## Scope

This note records read-only interoperability checks performed during the AI
Governance demo dataset implementation. It is intentionally separate from the
seed implementation.

Checked artifacts:

- Upstream AI RMF catalog at commit
  `56b1adba350b11f200636b94a64615b29fae33ed`
- Upstream mapping collection
  `mapping-collections/nist_ai_rmf_to_iso_42001/mapping-collection.json`

## Inputs and provenance

- Catalog file copied to
  `examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.json`
- Catalog SHA-256:
  `5d23b8f05ab5d8e96c552e2a9dcc1f0da9062fe9dcbe61b8de3136edf4cb703e`
- Catalog UUID:
  `1cead03a-d26a-400d-b16b-169816e2e592`
- Declared OSCAL version: `1.1.2`
- Upstream repository license: Apache-2.0

## Control ID verification

The following required control IDs exist in the upstream catalog, with statement
identifiers using the `_smt` pattern:

- `MG-3.1-009`
- `MP-1.1-008`
- `MS-2.7-016`
- `GV-4.1-003`
- `GV-1.2-003`

## Group ID vs control ID re-check

The upstream mapping collection references source controls such as `GV-1.1`,
`GV-1.2`, `MS-2.7`, and `MG-3.1` via `sources[].id-ref` with `type=control`.

When compared against actual control IDs in
`catalogs/nist_ai_rmf_gen_ai/1.0.0/catalog.json`:

- `unique_source_refs=49`
- `missing_from_catalog=49`
- `contains_GV-1.1=True`

Interpretation:

- These references are group- or family-level identifiers, not concrete control
  IDs from the source catalog revision.
- The mismatch is real and reproducible.

## Mapping validation diagnostics: independent vs cascading

Validation against the repository OSCAL Mapping validator (`1.2.1`) reports two
primary diagnostics:

1. `/mapping-collection/provenance/method`
   - `'manual' is not one of ['human', 'automation', 'hybrid']`
2. `/mapping-collection/mappings`
   - Fails the oneOf/anyOf branch with nested sub-diagnostics, including:
     - list where object is required in one branch
     - `target-gap-summary.unmapped-controls[0].with-ids` must be non-empty

Assessment of failure shape:

- The `provenance.method` value error is an independent schema violation.
- The `mappings` diagnostic is an aggregate branch failure that includes nested
  diagnostics; these nested diagnostics are related to schema-branch selection
  and constraints and can appear cascading.
- Therefore, reported mapping schema errors are a mix: at least one independent
  failure plus branch-level cascading diagnostics.

## Out of scope

- No upstream artifacts were modified.
- No compatibility adapters or import extensions were added in this task.

