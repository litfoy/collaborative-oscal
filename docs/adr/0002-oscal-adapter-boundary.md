# ADR 0002: Isolate OSCAL and Trestle behind an adapter boundary

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

OSCAL documents are interoperability artifacts whose structure and versions may evolve. IBM compliance-trestle is a useful open-source integration candidate, but it must not dictate domain modeling or become a required hosted dependency.

## Decision

Place OSCAL parsing, validation, canonical JSON representation, import/export, and any Trestle calls behind `packages/oscal`. Keep domain/application models independent of OSCAL serialization structures, and make Trestle an optional adapter.

## Consequences

The domain can evolve independently of OSCAL schemas and Trestle releases. The
package currently provides only deterministic document digests and query index
projections; it does not validate or import OSCAL. The adapter needs explicit
compatibility tests and a version support policy before full artifact handling is
implemented. No Trestle dependency is included.
