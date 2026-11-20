# Technical Debt Backlog — Collaborative OSCAL

This list is maintained by the Author and formatted by AI

| ID | Classification | Topic / Potential Follow-up | Status |
|---|---|---|---|
| TB-09e-01 | Minor | Typed stale-update responses and OpenAPI 409 declarations for Component Definitions (`component_definition_routes.py`). | Deferred |
| TB-09e-02 | Improvement | Simplify BFF client DELETE overloads for JSON 200 / HTTP 204 (`apps/web/src/lib/bff-client.ts`). | Deferred |
| TB-09e-03 | Minor | Consistent read snapshots for Component Definitions: document and relational projections across multiple queries. | Deferred |
| TB-09d/e-04 | Improvement | Declare `concurrency_version >= 1` database check constraints in ORM metadata as well. | Deferred |
| TB-09d/e-05 | Improvement | Separate frontend create and update input types; type mandatory `expected_version` for updates. | Deferred |
| TB-09d/e-06 | Minor / Docs | Update ADR 0022 and `docs/architecture/optimistic-concurrency.md` with the actual rollout/review status after Task 09, without changing normative rules. | Open; suitable for a small, separate documentation fix |
| TB-09d/e-07 | Improvement | Add explicit BFF contract tests for DELETE query tokens, structured 409 responses, and JSON/204 responses. | Deferred |
| TB-09d-08 | Improvement | `ProfileWorkspace.tsx`: clean up conflict-reload cache and reuse immutable revision data more efficiently. | Deferred |
| TB-09d-09 | Improvement | `profile-manager.test.tsx`: verify pending protection with an Add Source action that can actually be enabled. | Deferred |
| TB-09f-01 | Minor | Structured OpenAPI 409 responses for system/component updates. Combine with TB-09e-01. | Deferred |
| TB-09f-02 | Improvement | ORM constraints for system/component `concurrency_version`. Combine with TB-09d/e-04. | Deferred |
| TB-09f-03 | Minor | `SystemWorkspace.tsx`: clear old component conflict state when switching/discarding an editor; no demonstrated draft overwrite. | Deferred |
| TB-09f-04 | Improvement | Split `SystemWorkspace.tsx` into cohesive system/component editors while preserving independent tokens and drafts. | Deferred / UX overhaul |
| TB-09f-05 | Improvement | Strengthen system/component test assertions for complete rollback, audit fields, and token independence. | Deferred |
| TB-09g-01 | Minor | Typed OpenAPI 409 responses for implementation and dual-token association conflicts, including the correct aggregate ID. | Deferred |
| TB-09g-02 | Improvement | ORM check constraint for `ControlImplementationRecord.concurrency_version`; combine with other constraint items. | Deferred |
| TB-09g-03 | Improvement | Selectively consolidate duplicate implementation stale markers/error translation; **do not** introduce a new concurrency framework. | Deferred |
| TB-09g-04 | Minor | Consistent read snapshots for Implementations and Responsibilities (multiple queries). | Deferred |
| TB-09g-05 | Improvement | `ImplementationRegister.tsx`: refresh list cache after save/reload while preserving local draft/token guarantees. | Deferred |
| TB-09g-06 | Improvement | Add a lock compatibility test for two SSPs sharing a referenced implementation (`test_system_security_plan_concurrency.py`). | Deferred |
| TB-09g-07 | Improvement | Extend mapper rollback assertions to entire aggregates, audit fields, and responsibility row IDs. | Deferred |
| TB-SEED-01 | High | Product Decision | Define whether governance demo data is an immutable reference scenario or an editable starting point. Current strict seed cardinalities may block subsequent Compose initialization after legitimate user modifications. | Decision pending |
| TB-SEED-02 | Minor | Document safe cleanup of orphaned ai-governance-seed Docker containers after removal of the optional Compose service. Avoid destructive volume resets. | Deferred |
| TB-SEED-03 | Release Check | Verify EU AI Act catalog provenance, source version, scope, and redistribution rights before broader demo publication or distribution. Investigate the separate untracked catalog variant. | Deferred |


## B. Earlier Technical Debt / Release Hardening - if it will ever be released

| ID | Classification / Horizon | Topic |
|---|---|---|
| TD-OLD-01 | Release-relevant | Investigate and correct SSP `document_version` ordering when multiple publications share the same second-resolution `created_at`; distinct from `concurrency_version`. |
| TD-OLD-02 | Deferred | REST import: surface source provenance in API/UI, add ORM checks, clarify replay-vs-validation error precedence, and explicitly test JSON key ordering. |
| TD-OLD-03 | Deferred | Modularize larger REST import/mapping methods along domain boundaries only when needed. |
| TD-OLD-04 | Deferred / UX | Investigate Profile Builder performance for large catalogs; the CI timeout fix was not a product performance fix. |
| TD-OLD-05 | Release-relevant | Security/secrets/dependencies: independently verify Gitleaks findings and the working tree; reassess advisories (including the earlier `picomatch` dependency chain). No Git history rewriting without approval. |
| TD-OLD-06 | Release-relevant | Complete a needs-based review of third-party licenses, distribution/notice obligations, SPDX/REUSE gaps, and documentation/Code of Conduct attribution. |
| TD-OLD-07 | Deferred | SBOM generator: make relative output paths robust, complete script headers, and automate CycloneDX schema validation. |
| TD-OLD-08 | Release / Later | Publish SBOM as a release asset; before container distribution, assess complete OCI/OS/native-license coverage. Signing/attestation later. |
| TD-OLD-09 | Deferred (PO) | CI hardening: PostgreSQL tests on push, locked dependencies, no silent skips, and frontend build; **full CI/CD hardening intentionally deferred**. |
| TD-OLD-10 | Before formal Alpha acceptance | Manual browser E2E including REST curl/import/replay/publication, reproducible quickstart, and review of outdated MFA wording in the curl example. |
| TD-OLD-11 | After Alpha | Modularize large Python/React files based on domain cohesion (no shift to microservices). |
| TD-OLD-12 | After Alpha | Systematic Python type checking: an earlier optional mypy run showed 297 errors in 47 files; not currently an acceptance gate. |
| TD-OLD-13 | After Alpha | Add targeted Python docstrings (PEP 257), TSDoc, and optionally generated developer/API reference documentation. |
| TD-OLD-14 | Later | Improve frontend accessibility and consistent navigation/editor UX as relevant features are developed. |
