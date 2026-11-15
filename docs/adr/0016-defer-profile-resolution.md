# ADR 0016: Defer Profile Resolution

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

Profile Resolution turns a Profile and its imported Catalogs into a derived
Catalog. The application stores Profile selection semantics in OSCAL JSONB and
pins each ordered import to an immutable tenant-owned Catalog revision. A
resolver must preserve those normative requirements; successful parsing or
schema validation alone does not establish that it resolved them correctly.

The locked and installed Compliance Trestle version is 5.2.0. Isolated
experiments with its `ProfileResolver` verified that:

- A 1.1.3 Profile with a 1.1.3 Catalog and a 1.2.1 Profile with a 1.2.1 Catalog
  both ran through the resolver.
- A 1.2.3 Profile referencing 1.1.3 and 1.2.2 Catalogs, including together in
  one Profile, also ran. Additional 1.2.1 Profile experiments against 1.1.3
  and 1.2.2 sources ran as well. These are execution results, not verified
  compatibility guarantees.
- In every successful case, Trestle emitted OSCAL 1.2.1, irrespective of the
  Profile or source Catalog versions. No document was relabeled to claim its
  original version.
- Exact-ID selection and `with-child-controls: yes` worked in focused examples.
  Selecting a nested child alone emitted it without its parent, contrary to
  the ancestor-preservation behavior described in the current draft NIST
  Profile Resolution specification.
- Repeated imports selecting the same control produced duplicate control IDs.
  With different source definitions sharing an ID, the result was invalid and
  contained the later definition twice.
- Trestle's generated Profile model rejects non-empty `merge.combine` values;
  its merge implementation does not support custom grouping. Its Modify
  implementation logs and skips `removes`, so unsupported directives can be
  silently unapplied by the resolver.

Trestle's model and the application's OSCAL schemas can establish structural
validity for a declared version. They cannot establish correct selection,
hierarchy, collision resolution, merge, or modify semantics. The NIST Profile
Resolution specification is a work in progress and is distinct from the
published OSCAL Profile model and versioned JSON references.

## Decision

Defer general Profile Resolution. Do not implement a custom resolver, workaround,
compatibility adapter that changes normative content, or a partially correct
resolution feature. Preserve Compliance Trestle, the existing OSCAL version
dispatch and validation architecture, dependencies, and persisted application
data unchanged.

The maintained NIST OSCAL Java CLI is a candidate for a future, separately
approved evaluation. It is not integrated by this decision.

Profile Resolution does not block a future System Security Plan POC. Its
separate architecture review may consider explicitly selected,
revision-pinned requirements or direct catalog references as a restricted
baseline. That review must address baseline immutability, unambiguous control
identifiers, unsupported Profile semantics, and cross-document validation. It
must not present selected requirements as a fully resolved OSCAL Catalog.

## Reconsideration

Reconsider Profile Resolution only after an approved evaluation demonstrates,
for each advertised Profile and Catalog version combination and supported
directive, that the maintained resolver preserves exact source association,
selection and hierarchy semantics, repeated imports, conflict behavior, and
modifications without silent loss or alteration. The derived output must retain
an honest OSCAL version and pass matching structural and semantic checks.
Source loading must remain tenant-authorized, revision-pinned, isolated, and
read-only. Any resolver upgrade or alternative, including the NIST OSCAL Java
CLI, requires separate approval before adoption.
