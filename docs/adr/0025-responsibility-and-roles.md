# 0025: Responsibility roles and approval workflow for assessment artifacts

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

The project's central principle is that assessments stay independent: sharing a
safeguard or an implementation must not let one function decide another's
outcome (README, "Why Collaborative OSCAL?"). The README also lists fine-grained
stakeholder authorization and separation of duties as unfinished.

Current state of the code (reviewed 2026-11-21):

- ADR 0006 defines three tenant roles (`tenant_admin`, `catalog_editor`,
  `viewer`) mapped to five permissions (`tenant:read`, `tenant:manage`,
  `catalog:read`, `catalog:write`, `catalog:import`).
- The route modules for systems, implementations, SSPs, Assessment Plans and
  Assessment Results use the same `catalog:read` / `catalog:write` pair. Anyone
  who may author a plan may also author its results and publish both. Nothing
  distinguishes the person who documents a system from the person who assesses it.
- Mutable working records carry `created_by` / `updated_by`. The immutable
  snapshot tables (`system_security_plan_versions`,
  `assessment_plan_versions`, `assessment_result_versions`) carry `created_at`
  and a content digest, but **no identity of the person who published**.
- `GET /api/v1/tenants` already returns the permissions of the current user per
  tenant, so a UI can consume permissions without a new endpoint.
- Local demo mode has exactly one demo user (ADR 0015), so separation of duties
  cannot currently be demonstrated.
- ADR 0006 anticipated further roles (Auditor, Risk Owner, Control Owner,
  External Reviewer) without defining them.

Two concepts must stay separate:

- **Tenant authorization** (RBAC): what a signed-in person may do in the
  application. Enforced by the backend.
- **OSCAL parties, roles and responsibilities**: who is responsible for a
  control or task *as documented* in an OSCAL document. This is user-authored
  content and a planned feature, not a trust boundary.

## Decision

1. **Add domain permissions** next to the existing catalog permissions:
   `system:write`, `ssp:publish`, `assessment:write`, `assessment:review`,
   `assessment:publish`. `catalog:*` keeps governing catalogs, profiles and
   mappings.

2. **Add tenant roles** mapped centrally in `ROLE_PERMISSIONS`:
   - `system_owner`: read, `system:write`, `ssp:publish`.
   - `assessor`: read, `assessment:write`, `assessment:publish`.
   - `reviewer`: read, `assessment:review`.
   - Existing roles remain valid. `tenant_admin` keeps `tenant:manage` and
     `catalog:*` but does **not** implicitly receive `assessment:review`, so an
     administrator is not a universal approver. See open question 2.

3. **Introduce review requests** for Assessment Plans and Assessment Results
   (not for SSPs in this iteration). A review request is a tenant-scoped record
   with: subject type and id, `content_sha256` of the submitted working state,
   `submitted_by`, `submitted_at`, `decision` (`pending`, `approved`,
   `rejected`, `withdrawn`), `decided_by`, `decided_at` and a comment.
   Decided requests are immutable; a new decision requires a new request.

4. **Gate publication on approval.** Publishing an AP or AR snapshot requires an
   `approved` review request whose `content_sha256` equals the digest of the
   current working state. Any later edit invalidates the approval. The existing
   substantive-content digest logic (ADR 0020) is reused.

5. **Enforce separation of duties in the service layer.** The deciding reviewer
   must differ from the submitter and from the identity in `updated_by` of the
   submitted state. The policy is fixed in this iteration (no per-tenant
   switch).

6. **Record the publisher.** Add nullable `published_by` and `approval_id` to the
   three snapshot tables. Historical rows stay `NULL`; no history is rewritten
   or backfilled.

7. **Keep approvals out of the OSCAL documents.** Review state is application
   workflow state. It is stored relationally, not inside `document`, so snapshot
   digests and exports are unaffected.

8. **API and errors.** New endpoints create review requests, record decisions and
   list them per subject. Rejected operations return stable error codes in the
   shared error envelope (for example `approval_required`, `approval_stale`,
   `separation_of_duties`), modelled on the existing `stale_update` response.
   The backend is authoritative; the UI uses the permissions from `/tenants`
   only to hide or disable actions and to show the reason code.

9. **Migration.** An Alembic migration adds the tables and columns. Existing
   memberships keep their roles and their current authoring ability, but AP and
   AR publication now requires an approval for every role.

## Consequences

- Positive: the independence principle is enforced instead of only documented.
  Publications record who published and on what approved content. Reviewers can
  be shown exactly which version they approved.
- Positive: the permission matrix is explicit and testable (role x action,
  table-driven), consistent with the project's test style.
- Negative: a tenant needs at least two people to publish AP/AR. This is
  deliberate but awkward for very small teams and for demos.
- Negative: more UI surface (review state, disabled actions with reasons, a
  reviewer inbox) and more migration and seed work.
- Negative: local demo mode needs more than one identity to show the feature
  (see open question 5).
- Tenant-wide roles cannot express "this person must not assess the system they
  own". Only the object-level rule (author cannot approve) is enforced.

## Alternatives considered

- **Hide actions in the UI only.** Rejected: contradicts the rule that backend
  enforcement is authoritative (ADR 0020).
- **Derive permissions from OSCAL responsible parties.** Rejected: document
  content is user-authored and must not grant access.
- **External policy engine (for example OPA).** Deferred as disproportionate for
  an alpha.
- **Per-system access control lists now.** Deferred; larger model change.
- **Configurable multi-stage workflows.** Deferred; one review step first.

## Open questions

1. One role per membership (current unique tenant/user constraint) or several
   roles per membership? Several roles are more flexible but change the
   membership model.
2. Should `tenant_admin` receive review rights, or stay a pure administrator?
3. Should a tenant be allowed to relax the four-eyes rule (explicit, recorded
   exception) for very small teams?
4. Should SSP publication also require review?
5. How should the local demo show two or more personas? Options: use the
   optional local Keycloak profile with several users, or add a clearly
   local-only persona switch. The second must not weaken the existing demo-mode
   guards (ADR 0015).
6. Should the approval digest also cover pinned references (SSP/AP versions) or
   only the working content?

## Notes

- Suggested order: (a) permissions, roles, `published_by` and the
  permission-matrix tests; (b) review requests and the publication gate;
  (c) UI states using the permissions already returned by `/tenants`;
  (d) demo personas.
- Wording stays careful: an approval records a workflow decision in this
  application. It is not evidence of regulatory compliance.

## Deferred

- Per-system or organizational-unit scoping of roles.
- Configurable workflows, delegation, notifications.
- Append-only general audit log.
- Time-limited external reviewer access.
- Export of responsible parties and roles into OSCAL metadata, together with
  Parties/Roles/Responsibilities management from the roadmap.