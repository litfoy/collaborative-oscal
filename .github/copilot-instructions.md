# Repository instructions

## Architecture

- Treat this repository as a modular monolith. Do not introduce services, queues, or deployment infrastructure without a
  demonstrated requirement.
- Keep GRC domain rules independent of FastAPI route handlers and persistence details.
- Keep OSCAL parsing, validation, serialization, and IBM compliance-trestle integration behind the `packages/oscal`
  boundary. Domain entities must not mirror OSCAL serialization models.
- For application-authored OSCAL documents, reuse maintained Compliance Trestle-generated models wherever
  version-compatible. Retain domain-to-OSCAL mapping, independent validation against the official version-specific NIST
  JSON Schema, and application-level integrity checks. Preserve imported normative documents and immutable historical
  snapshots without Trestle reserialization. Future Assessment Plans, Assessment Results, and POA&M implementations must
  follow this convention from the beginning wherever supported.
- Keep tenant identity explicit in authorization and data access designs. Never rely on client-provided tenant IDs
  without an authorization check.
- Authentication validates configured OIDC access tokens, persists external identities and tenant memberships, and provides
  trusted tenant context and catalog:read/catalog:write authorization. Catalog browsing, Profiles, implementation registers,
  Systems, SSP/AP/AR workflows, native Assessment Results REST import, and optimistic concurrency implementations for
  Assessment Plans, Assessment Results, SSPs, Profiles, and Mapping Collections are implemented. Independent contention and
  verification review coverage is currently established only for Assessment Plans and Assessment Results.
  Do not imply that unimplemented GRC areas such as catalog editing, managed evidence, risk/POA&M, or fine-grained Party/Role
  governance are complete.

## Implementation standards

- Use Python type annotations and Pydantic for validated API configuration/contracts; use TypeScript strict mode for the
  web application.
- Keep API contracts explicit and version changes intentional.
- Use environment variables for configuration. Never commit secrets, credentials, or production-like defaults.
- Apply least privilege, secure browser/API defaults, and tenant-aware isolation at each data-access boundary. Do not
  trust tenant IDs or roles from request headers or token claims.
- Add focused tests for behavior and run the relevant test, lint, and type-check commands before completing a change.
- Prefer maintained open-source dependencies and update lockfiles with their manifests.
- Keep changes focused; document meaningful architectural choices in `docs/adr/`.
- For mutable aggregate concurrency changes, follow `docs/adr/0022-aggregate-optimistic-concurrency.md` and
  `docs/architecture/optimistic-concurrency.md`.

## Current scope

The API exposes public `/health`, bearer-protected identity/tenant endpoints, tenant-scoped catalog read endpoints,
Catalog/Component/implementation/System/SSP/AP/AR workflows, and native Assessment Results REST import where implemented.
OIDC access-token verification, identity/membership persistence, tenant-scoped roles, trusted tenant-context dependencies,
and the authenticated BFF are implemented. The Next.js app is an OIDC Backend-for-Frontend (openid-client, encrypted
HttpOnly cookie session; tokens never reach the browser). Catalog import also remains available through
`python -m app.cli`. Catalog editing, managed evidence, shared Parties/Roles/Responsibilities, risk/POA&M, public user
management, and machine identities are not complete. Control references use `catalog_id + revision_id + oscal_control_id`.
See ADR 0007. Optimistic concurrency implementations exist for Assessment Plans, Assessment Results, SSPs, Profiles, and Mapping Collections;
independent contention and verification coverage is currently established only for Assessment Plans and Assessment Results.

### Domain-Oriented User Experience

- The application is intended for security and privacy professionals.
- Normal authoring workflows must not require users to manually enter internal identifiers, UUIDs, JSON structures, or
  API payloads.
- Use existing domain objects, searchable selectors, structured editors, and human-readable references.
- Raw OSCAL JSON may be exposed for optional technical inspection and export, but it must not substitute for a
  functional domain-oriented user interface.
- A successful API integration is not sufficient evidence of a completed user-facing feature.
- Verify representative workflows through the actual graphical user interface.

Dependency Governance

- Prefer existing dependencies and actively maintained libraries over custom implementations.
- Before adding, replacing or upgrading dependencies, verify current stable versions, maintenance status, known
  vulnerabilities, license obligations and compatibility using authoritative upstream sources.
- Consider transitive dependencies and the intended distribution model.
- If a dependency is abandoned, deprecated, vulnerable, incompatible or has unclear licensing, report alternatives and
  request maintainer approval before proceeding.
- Do not introduce new dependencies without explicit approval.
- Keep dependency declarations, lockfiles, license inventories and relevant tests consistent.
- Never silently accept security or licensing risks, force incompatible resolutions or bypass security checks.

# Implementation and acceptance rules

- Implement only the approved task scope.
- Follow the existing architecture and applicable ADRs.
- Preserve native OSCAL semantics and historical document immutability.
- Maintain tenant isolation and explicit identity relationships.
- Add meaningful positive and negative regression tests.
- Verify migrations, backend and frontend compatibility where applicable.
- Report exact changes, verification results and remaining limitations.
- Do not commit or push without maintainer approval.
- STOP after reporting. Do not start the next task.

## Reporting Discipline

- Keep reports concise and decision-oriented.
- Report verified findings, changes, test results, unresolved risks and required decisions.
- Do not repeat unchanged architecture, requirements or previously accepted findings.
  
## Verification Integrity

- Never claim that tests or validations passed unless they were actually executed successfully.
- Report the exact commands, exit codes, passed, failed and skipped test counts.
- Distinguish partial verification from complete acceptance.
- Never treat skipped tests as successful verification.