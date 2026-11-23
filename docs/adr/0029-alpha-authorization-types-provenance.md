# ADR 0029: Resource Authorization, Assessment Types, Provenance, and Personal SoD for Alpha

- Status: Proposed — not approved or implemented
- Date: 2026-11-24 (revision 2, consolidating the independent architecture review of 2026-11-23)
- Scope: Collaborative OSCAL Alpha
- Principle: **Shared compliance data. Independent assessments. Verifiable decisions.**

## Context

The current implementation (verified in the repository) has:

- OIDC identities, tenant memberships and three tenant roles (ADR 0006). `tenant_admin` receives the entire
  `Permission` enumeration (`application/authorization.py`).
- A single fixed demo identity that must hold `catalog_editor` (ADR 0015, `api/dependencies.py`, `authentication/demo.py`).
- One permission, `catalog:write`, guarding every System, SSP, implementation, AP and AR mutation, including
  publication. The BFF derives write affordances from `catalog:write`.
- Route-level membership checks in a session separate from the business mutation.
- `created_by`/`updated_by` on working records only. Published SSP/AP/AR versions do not record a publisher.
  Implementation responsibilities are deleted and reinserted on change, so no assignment history exists.
- Immutable version and pin triggers, but no database-enforced chain between AP/AR pins, no write-once
  implementation-to-system binding, and implicit `catalog_revisions ... FOR UPDATE` locks inside several triggers.
- SSP association and SSP publication lock the SSP before the System.
- Publication returns an existing version on a normalized-digest hit without further checks.
- One PostgreSQL role that owns the schema, runs migrations and serves the API.
- A demo seed CLI that attributes all seeded content to a caller-supplied `--actor-id`.

Alpha must demonstrate real backend authorization and one enforced personal Separation-of-Duties (SoD) rule with
switchable fictional users, without building a user-management product, a grant-approval workflow, an AR-review
workflow or general event sourcing. A self-assessment by an implementer is legitimate. A claim of personal
independence requires stronger, recorded conditions. OSCAL roles and parties document business responsibility;
they never grant application access.

## Decision summary

1. Authentication, authorization and OSCAL responsibility stay separate. One server-side policy, evaluated inside
   the business transaction, governs all entry points (§1).
2. Explicit, persisted resource grants replace `catalog:write` for system-scoped work. Assessor grants bind to one
   published AP version. Grants are issued only by an authenticated provisioning operator through a CLI (§2, §3).
3. Every AP has an immutable `self_assessment` or `independence_claimed` type, exported as a namespaced OSCAL
   property (§4, §5).
4. SOD-ALPHA-01 v1 is a conservative, system-wide personal conflict check, evaluated at each independent AR
   publication with results `verified`, `conflict` or `unverifiable` (§6).
5. A minimal, database-enforced participation journal makes provenance capture fail closed for every writer (§7).
6. Separate database roles distinguish schema ownership, runtime writes and grant provisioning (§8).
7. Relational invariants, a deterministic lock order and transactional journal positions make the decision race-safe
   (§9, §10).

## 1. Authentication, authorization and OSCAL responsibility

- OIDC and demo authentication both resolve to a trusted internal actor and an active tenant membership. Both use
  the same resource authorization policy and enforcement path. There is no separate demo policy.
- The service receives its principal from the authentication adapter only — never from a caller-selected user ID,
  tenant header, role claim, OSCAL party or CLI argument.
- Authorization is re-evaluated in the **same SQLAlchemy session and PostgreSQL transaction** as the mutation, with
  the locks in §10. Route dependencies may reject early but cannot authorize. BFF affordances are hints (§12).
- Deny by default. Every lookup is tenant-qualified. A request's system ID never routes an unrelated record.
- OSCAL parties, roles, `responsible-parties` and `responsible-roles` remain documentary. An internal-user-to-party
  association may be kept, but it never grants API access. Governance disciplines (data protection, information
  security, AI safety) may appear as OSCAL organization parties, not as technical roles.

## 2. Actors, identities and provisioning authority

**Actor kinds.** `user_identities` gains an immutable `actor_kind`:

- `human`: resolved from a configured OIDC issuer or a reserved demo persona.
- `technical`: reserved issuer `urn:collaborative-oscal:technical` and a fixed subject per purpose (for example
  `demo-seed`, `demo-provisioner`). Technical identities cannot authenticate through the API, cannot be resolved from
  an OIDC token, cannot hold resource grants and cannot appear in an independent assessment actor set. A database
  CHECK ties `actor_kind = 'technical'` to the reserved issuer.

The seed CLI no longer accepts `--actor-id`. Seeds write as the technical seed actor and may only write in tenants
listed for that actor in an owner-managed allowlist (§8). Seeds never create human actions, confirmations or
decisions on behalf of personas. They may create self-assessment or legacy demo content, never an
`independence_claimed` publication.

**Identity assurance.** Each human identity has `identity_assurance` (`distinct` by default, or `ambiguous`). The
provisioning operator may mark known aliases, replacement accounts or unresolved issuer transitions as `ambiguous`.
Accounts are never joined by e-mail or display name.

**Provisioning authority.**

- Grants are issued and revoked only through a provisioning CLI using the `oscal_provisioner` database role (§8). The
  API runtime role cannot write grants.
- In OIDC mode, the CLI authenticates the operator by validating an access token with the existing configured
  validator. The grantor is the identity resolved from that token. No grantor UUID, manifest field or CLI argument
  is accepted.
- The operator must be listed for the tenant in `provisioning_operators`, an owner-managed table that is read-only to
  the runtime and provisioner roles.
- In demo mode, only the technical `demo-provisioner` actor may apply the checked-in demo grant manifest, and only to
  reserved demo targets.
- Issuance requires a grantor different from the beneficiary (database CHECK), an active `human` beneficiary
  membership, an existing target, and no wildcard or future-resource scope.
- Assessor issuance for an `independence_claimed` AP version runs SOD-ALPHA-01 for the beneficiary alone and is
  denied on `conflict`. An `unverifiable` result is reported but does not block issuance; publication decides.
- Grants are never reactivated. Revocation is terminal and records the authenticated revoker. Re-issuing creates a
  new grant row. Replaying a manifest never recreates a grant whose manifest entry was revoked.
- **Alpha limitation:** grant provisioning is CLI-only. A System or AP version created in the GUI is unusable for
  system-scoped work until an operator provisions it. There is no grant-management UI.

## 3. Resource capabilities and operation matrix

Resource capabilities are a separate type and never members of the tenant `Permission` enumeration. A resource check
neither falls back to nor additionally requires `catalog:write`. Active membership in the resource tenant is always
required.

| Capability | Target | Purpose |
|---|---|---|
| `system:implement` | System | Implementation-side authoring |
| `system:plan_assessment` | System | AP authoring and publication |
| `system:self_assess` | System | Additional precondition for self-assessment and legacy AR work |
| `assessment:assessor` | One published AP version | AR work against exactly that pin |

| Operation | Required authority | Notes |
|---|---|---|
| Browse, validate without saving, list or export versions | Existing tenant read policy (`catalog:read`) | No mutation |
| Catalog import, Profiles, Mapping Collections, Component Definition library | Existing `catalog:write`/`catalog:import` | Library authorship is not system participation |
| Create System | `catalog:write` (pre-resource exception) | Grants no rights on the new System; starts complete coverage (§7) |
| Edit System (characteristics, boundary, status) | `system:implement` | Journaled participation (§6) |
| Create/edit system component; adopt component definition | `system:implement` | |
| Create/edit **unbound** implementation and its responsibilities | `catalog:write` | Unbound status checked under the implementation lock (§10) |
| Edit **bound** implementation or its responsibilities, through any route | `system:implement` on the bound System | Includes the generic `/implementations/{id}` route |
| Create/edit SSP, publish SSP version | `system:implement` on the SSP System | |
| Attach implementation to SSP | `system:implement` on the SSP System; first binding additionally requires `catalog:write` | ADR 0017 baseline, component and organization checks retained |
| Remove SSP association | `system:implement` on the SSP System | Binding stays (write-once) |
| Confirm or decline one's own named responsibility | The named human assignee with active membership | Self-scoped; no grant (§6) |
| Create typed AP, edit AP, publish AP version | `system:plan_assessment` | For `independence_claimed`, a known `conflict` of the acting planner is rejected early |
| Create, edit, import or publish AR, including import replay | `assessment:assessor` on the AR's exact pinned AP version | Self/legacy pins also need `system:self_assess`; independent publication also needs `verified` (§6) |
| Issue or revoke a grant; mark identity assurance | Provisioning authority (§2) | CLI only |
| Tenant and membership bootstrap | Existing operator CLI | Unchanged; `tenant_admin` receives no resource capabilities |

No protected mutation is permitted by implication. There is no `assessment:reviewer` grant.

## 4. Immutable assessment type and version-bound assessor grants

- Every new AP is created with exactly one immutable `assessment_type`: `self_assessment` or `independence_claimed`.
  Changing it requires a new AP.
- `legacy_unclassified` is assigned by migration to pre-existing APs only. A database trigger rejects inserting a
  legacy or null type after activation, and the context trigger rejects any type change.
- Each published AP version stores a copy of the type, bound to the AP by a composite FK. An AR inherits the type of
  its pinned version. There is no client-writable AR classification.
- An `assessment:assessor` grant names one published AP version. AR create, edit, import and publish are allowed only
  when the AR's pin equals the grant's version. Work against a later AP version requires a new grant.
- There is no scope comparison or containment algorithm. Revocation stops further work on that pin. It does not
  alter earlier versions or recorded decisions.
- `self_assessment` and `legacy_unclassified` pins: assessor grant plus `system:self_assess`. Implementation
  participation does not disqualify the actor. There is no independence badge.
- `independence_claimed` pins: assessor grant plus SOD-ALPHA-01 `verified` at publication. An independence claim is
  not itself a verified finding. A draft never counts as a passed check.
- An AP creator or planner does not become an assessor by virtue of that role.

## 5. OSCAL representation and import

**Property.** Typed AP and AR candidates and new snapshots carry exactly one `metadata.props` entry (OSCAL 1.2.1
extension syntax):

- `name`: `assessment-type`
- `value`: `self_assessment` | `independence_claimed`
- `ns`: `https://github.com/litfoy/collaborative-oscal/ns/assessment`

The `ns` value is an opaque, permanent identifier. It is never dereferenced and is not changed if repository hosting
moves. Its semantics are documented in the repository.

The property communicates the declared engagement type only. It is not a NIST vocabulary and not a certified or
verified independence verdict. The SoD determination stays outside OSCAL.

**Authoring.** The AR derives the value from its pinned AP version. Native `import-ssp`/`import-ap` semantics and
existing reference checks are unchanged. Use the compatible Trestle models, independent official 1.2.1 schema
validation and application integrity checks; schema validity does not check the type relationship. Legacy outputs
omit the property and are labelled **legacy unclassified / non-independent** in the UI. Historical snapshots are never
reserialized or backfilled.

**Native AR import (amends ADR 0023's accepted subset narrowly).** ADR 0023's strict subset, exact `import-ap.href`,
draft-only creation, source identity, pre-mapping canonical digest, submission provenance and replay contract remain.
There is no original-byte archival. Changes:

- `metadata.props` is accepted only as at most one entry of the exact project shape (`ns`, `name`, `value`). Any
  other, duplicate (even identical), malformed or foreign property is rejected, never dropped.
- `self_assessment` pin: absent or `self_assessment` accepted. A missing value is added only to application-authored
  output.
- `legacy_unclassified` pin: any `assessment-type` property is rejected.
- `independence_claimed` pin: import is rejected. In Alpha, externally authored contributions cannot reach
  `verified`, so such a draft could never be published (PO decision D3).
- Authorization (§3) is checked before an existing aggregate is returned on replay, including in the new transaction
  after a uniqueness race.
- The authenticated submitter is recorded as the proven submitter only, not as the external author.

## 6. SOD-ALPHA-01 v1: system-wide personal conflict rule

**Personal implementation activity on System S** is any journaled effective write (§7) by a human actor to:

1. System S itself, including characteristics, boundary and status (PO decision D2);
2. a system component of S, including component-definition adoption;
3. an implementation bound to S, including its pre-binding history (§7), binding, and changes to responsibilities;
4. an SSP of S, or an SSP association of S, including attach and remove.

It also includes a **confirmed responsibility**: the named assignee personally confirmed it, or assigned themselves,
on an implementation bound to S.

The following are **not** personal implementation activity:

- reads, validation, ineffective writes and no-ops;
- SSP or AP version publication without a content change;
- reusable library authorship;
- a responsibility assigned by someone else and not confirmed (the assignee's decline is recorded and is not
  activity);
- role-only responsibilities.

Documentary OSCAL responsibilities are exported unchanged regardless of confirmation state.

**Unconfirmed assignments (PO decision D1).** While an actor in the checked set is the named assignee of an active,
unconfirmed responsibility on an implementation bound to S, the result is `unverifiable`, not `conflict`. Removal or
the assignee's own decline clears this effect, because no personal participation was ever recorded. A third party
therefore cannot permanently disqualify an assessor. Confirmation is permanent participation. Assignments, decisions
to confirm or decline, and their actors are journaled separately.

**Checked actor set** for a new version of an AR pinned to AP version V:

- (a) the AP-side actor set stored immutably at V's original publication: the AP creator and every actor with an
  effective AP edit before that publication, including reverted edits. Later AP editors never join V's set.
- (b) the AR creator, the import submitter and every actor with an effective AR edit through this request, including
  actors whose grants were later revoked.
- (c) the requesting publisher.

An unused grant, a documentary party or publication alone is not assessment work.

**Result.** Evaluated over System S's journal through the cut-off (§10):

| Result | Meaning | Independent AR publication |
|---|---|---|
| `conflict` | A checked actor has recorded personal implementation activity on S | Denied |
| `unverifiable` | Coverage of S is incomplete (legacy start, bound pre-instrumentation implementation, recorded gap); a checked actor is `technical` or `ambiguous`; an active unconfirmed assignment names a checked actor; or the AR carries import provenance | Denied |
| `verified` | Coverage is complete to the cut-off and none of the above applies | Permitted if all other checks pass |

`conflict` takes precedence over `unverifiable`. Missing history never yields `verified`.

`verified` means only that the recorded personal-conflict test passed for recorded internal actors. It does not
certify organizational independence, absence of collusion or aliases, off-platform collaboration, competence,
correctness of findings, or any review or approval. UI and reports use wording such as “Personal independence check
passed (recorded history)”. In demo mode they add “demo accounts”.

The same rule evaluates early rejections: independent AP creation or edit by a conflicted planner, and assessor
issuance. The decisive evaluation is repeated on every independent AR publish request. Self-assessment and legacy
paths do not evaluate it.

**Determination record.** Each successful independent AR publication stores an immutable determination:

- result `verified` and rule `SOD-ALPHA-01 v1`;
- System, cut-off position and coverage origin;
- checked actor IDs;
- AP version, new AR version and publisher;
- server time and authentication mode.

Later mutations affect only later publications.

## 7. Database-enforced participation journal (fail closed)

This is a minimal participation log, not event sourcing. Current state stays in existing tables and is never rebuilt
from events.

**Actor context.** Every protected transaction runs `SET LOCAL` for `collaborative_oscal.actor_id`,
`collaborative_oscal.tenant_id` and `collaborative_oscal.operation` through one shared helper. This applies to API,
CLI, seed and nested savepoint writers alike.

**Guard triggers.** BEFORE INSERT/UPDATE/DELETE triggers on the protected tables raise an error when:

- the actor context is missing;
- the actor is unknown;
- the context tenant differs from the row tenant;
- a `human` actor lacks an active membership in that tenant;
- a `technical` actor writes outside its owner-managed tenant allowlist.

Protected tables: `information_systems`, `system_components`, `control_implementations`,
`implementation_responsibilities`, `system_security_plans`, `system_security_plan_implementations`,
`assessment_plans`, `assessment_results`, the three `*_versions` tables, `resource_grants` and the decision table.

Code that does not set the context — including pre-cut-over API instances, old CLIs and forgotten paths — therefore
fails closed. The guard is completeness and defence in depth; authorization remains the service's job (§1).

**Capture triggers.** AFTER ROW triggers, `SECURITY DEFINER` and owned by `oscal_owner` with a fixed `search_path`,
append one `provenance_events` row per effective row change. Each row records:

- tenant, System (nullable) and implementation (nullable);
- subject table, row ID and operation;
- changed content columns;
- actor, actor kind and operation label;
- for responsibilities: the assignee, kind and confirmation state;
- `clock_timestamp()`.

Bookkeeping-only changes (`updated_at`, `updated_by`, `concurrency_version`) produce no event. Rolled-back
transactions leave no events. Classification into SoD categories happens in versioned application code (§6) from the
captured facts, so domain rules stay out of the database.

**Positions and coverage.**

- Inserting a System creates its `system_journal_heads` row (`last_position`, `coverage_origin = complete`) and a
  creation event at position 1.
- An event with a System takes the next position by updating that head row. The head row lock is held to commit, so
  positions are gapless and follow commit order within a System. A unique index on `(system_id, position)` enforces
  this.
- Events on unbound implementations have no System. They are ordered under the implementation row lock and keyed by
  implementation ID.
- Each implementation stores an immutable `provenance_complete` flag: true when inserted after activation, false for
  pre-existing rows.
- **Binding** (write-once `system_id` NULL→S) records a binding event at a System position. That implementation's
  earlier unbound events become part of S's history through that position. Binding an implementation with
  `provenance_complete = false` records a permanent coverage-gap event on S.
- Nothing — removal, reseed, revocation, a later marker or a fresh System — clears a gap or recorded participation.
- Pre-existing Systems receive `coverage_origin = legacy_gap` and can never yield `verified` in Alpha.

**Publication facts.** New SSP/AP/AR version rows get:

- `published_by`, filled by trigger from the actor context and NOT NULL for new rows. Legacy rows stay NULL; no
  publishers are invented.
- `document_sha256`: canonical JSON SHA-256 of the entire stored document, including UUID, version and last-modified.
  It identifies JSON content, not transmitted bytes.

The existing normalized `content_sha256` stays for deduplication only. AP versions additionally store their
immutable AP-side actor set (§6 (a)).

## 8. Database trust boundary and privileges

| Role | Used by | Privileges |
|---|---|---|
| `oscal_owner` | Alembic migrations, owner-only administration (operator and technical-actor allowlists) | Owns schema, functions and triggers; never used by the API, business CLIs or seeds |
| `oscal_runtime` | API, business CLI, seeds | DML on working tables; INSERT only on version and decision tables; no direct privileges on `provenance_events`, journal heads, `resource_grants` writes or allowlists; column-limited UPDATE on `user_identities` (no `actor_kind`, `identity_assurance`); not owner, so it cannot disable triggers or TRUNCATE |
| `oscal_provisioner` | Provisioning CLI and demo grant manifest | INSERT and terminal revocation UPDATE on `resource_grants`; UPDATE of `identity_assurance`; SELECT where needed |

Append-only protection of events, versions, decisions and grant history comes from privileges plus triggers.

**Deployment implications.**

- Compose and development setups must create the three roles.
- Migrations run with owner credentials. The API and seeds receive runtime credentials. The provisioning CLI receives
  provisioner credentials.
- No runtime component holds owner credentials.
- Integration tests run business operations as `oscal_runtime` to prove the privilege limits.

**Limits.**

- `oscal_owner`, superusers, database administrators and backups are inside the trust boundary and can rewrite
  history.
- A compromised runtime process can set a false actor context. The journal guarantees completeness and attribution as
  asserted by the trusted application, not tamper evidence.
- External tamper-evident audit is out of scope for Alpha.

## 9. Relational invariants

Composite FKs (with the supporting unique keys where missing), CHECKs or triggers enforce:

1. AP: `(tenant, ssp_id, system_id)` → SSP; `(tenant, ssp_id, ssp_version_id)` → SSP version.
2. AP version: `(tenant, ap_id, ssp_version_id, assessment_type)` → AP.
3. AR: `(tenant, ap_id, system_id)` → AP; `(tenant, ap_id, ap_version_id)` → AP version.
4. AR version: `(tenant, ar_id, ap_version_id)` → AR.
5. Implementation `system_id` and `system_component_id` are write-once (NULL→value) and immutable afterwards.
6. AP type: immutable, and non-legacy for inserts after activation.
7. Grants: capability-to-target shape CHECK; `(tenant, system_id)` → System; `(tenant, ap_id, ap_version_id)` → AP
   version; `(tenant, beneficiary)` → membership; grantor ≠ beneficiary; a partial unique index allows one active
   grant per capability, target and beneficiary; revocation is terminal.
8. Responsibility assignee `(tenant, user_id)` → membership (existing). Confirmation may be set only by the assignee
   actor (trigger compares with the actor context).
9. Determination: unique per AR version; references consistent with rule 4.

The migration preflight lists existing rows that violate rules 1–5. The migration fails rather than auto-repairing.

## 10. Transactions, lock order, positions and publication

One PostgreSQL transaction (READ COMMITTED) covers authorization, mutation, journal capture, snapshot and decision.
Nested services, seed savepoints and CLIs share the caller's connection. Route lookups, grant caches and ADR 0022
tokens are not serialization boundaries. A transaction touches at most one System.

**Lock order.** Acquire every explicit lock before the first DML statement, in this order, sorting rows of one class
by ID:

1. Membership rows of the acting actor, named assignees and the grant beneficiary: `FOR SHARE`, with the query
   filtering on `status = 'active'`. Deactivation takes `FOR UPDATE` on that row only.
2. Relevant grant rows: `FOR SHARE`, filtering on active status. Revocation takes `FOR UPDATE` on that row only.
3. The `information_systems` row: `FOR UPDATE`. This is the system fence for every write with a System, including AP
   and AR edits and publications.
4. Aggregates parent before child: SSP → AP → AR.
5. Profile → catalog revision, `FOR UPDATE`, taken explicitly whenever the transaction will fire a trigger that locks
   `catalog_revisions` (SSP, implementation, mapping member and component-definition source triggers). The trigger's
   re-lock is then a no-op.
6. System component and component-definition snapshot.
7. Implementations.
8. Association and responsibility rows.
9. Journal head row: taken implicitly by the capture trigger on the first DML, always last.

This order replaces the existing SSP-before-System path in association and SSP publication; it is not layered on top
of it.

**Restarts.**

- An unbound implementation edit locks the implementation, then re-checks `system_id IS NULL`. If the implementation
  has meanwhile been bound, the transaction rolls back and restarts with the system fence first.
- Binding locks the System before the implementation.
- After any lock wait, re-read bindings, membership, grants, coverage and history. Do not reuse stale ORM state.
- Deadlocks, serialization failures and routing changes restart the whole transaction, including reauthorization,
  with a bounded retry count.
- ADR 0022 expected-version checks, stale responses, no-op semantics and token behaviour are preserved. Journal
  positions do not bump the System editing token.

**Cut-off.** While holding the system fence, independent AR publication evaluates S's journal through `last_position`
(the last committed position before its own publication event) plus the pending publisher. It then inserts the
snapshot, the determination and the publication event in the same commit.

- If a conflicting mutation commits first, the publication sees it.
- If the publication commits first, a later conflict does not invalidate the historical decision.

**Publication and idempotence.**

- Every publish request is authorized first.
- For an independent AR, the current request's actor set (current publisher included) is evaluated even when the
  normalized digest already exists. A now `conflict` or `unverifiable` request is denied.
- An allowed request with an existing digest (including A→B→A) returns the original version, publisher and
  determination, marked `reused`. It creates no snapshot, publication event, actor-set change or token bump.
- A reused AP version keeps its original AP-side actor set.

## 11. Legacy data

- Pre-existing APs become `legacy_unclassified`, which is not selectable for new APs and is not a retroactive claim of
  self-assessment. Legacy APs and ARs follow the self-assessment authorization path, never gain an independence badge
  and can never become `independence_claimed` by mutation, import or administration.
- Historical SSP/AP/AR snapshots and exports remain byte-for-byte unchanged in stored JSON. No type properties,
  publishers or contributors are backfilled.
- Pre-existing Systems are `legacy_gap`, and pre-existing implementations are `provenance_complete = false`. History
  before activation is unknown, not conflict-free.
- Existing seed history is not reassigned. The Alpha showcase uses a newly created, fully covered System.
- An attributable operator attestation of earlier history is out of scope for Alpha.

## 12. UI available actions and demo personas

**Available actions.** A read-only endpoint, for example `GET /tenants/{tenant_id}/available-actions?resource_type=…&resource_id=…`,
returns the actions the current actor may attempt on one resource. It is computed by the same policy, including an
SoD pre-check for independent AR publication. For the current actor it returns reason codes such as `missing_grant`,
`sod_conflict` or `sod_unverifiable`. These are hints only. The BFF replaces its `catalog:write`-based write
affordances with this endpoint for system-scoped resources.

**Demo personas.** Seven to ten reserved fictional `human` identities with fixed memberships and roles, and grants
applied from the checked-in demo manifest by `demo-provisioner`.

- The BFF keeps the persona choice in an integrity-protected, HttpOnly, browser-scoped cookie, changed only by a
  CSRF-protected same-origin POST. Switching refreshes the actor and available actions and discards pending actions
  from the previous persona.
- The BFF sends the server-only demo credential plus a persona key it constructs itself from a server-side allowlist.
  It never forwards caller-supplied identity headers.
- The API accepts the persona key only in demo mode. It verifies the reserved identity, tenant and expected active
  membership, and fails closed on any mismatch. In OIDC mode, a persona key is rejected.
- There is no process-global selection, cross-tenant access, shared-secret login in OIDC mode or provider-failure
  fallback.

This amends ADR 0015 in three points:

1. multiple reserved identities instead of one;
2. reserved roles other than `catalog_editor`;
3. the demo seed may apply grants through the technical provisioner.

ADR 0015's loopback, protected-network, dedicated-database and server-only-secret constraints remain. Demo mode still
provides no per-person accountability: it demonstrates different accounts, not different humans. Determinations made
in demo mode record `auth_mode = demo`.

## 13. OIDC transition

1. **Preflight (read-only):** inventory identities, memberships, Systems, APs, legacy classification, coverage gaps
   and rule-1–5 violations (§9).
2. **Prepare roles:** create the three database roles and credentials. The operator-allowlist entries are added by
   the owner.
3. **Migrate:** run the migration as `oscal_owner`. It adds the schema and triggers, classifies legacy rows and marks
   coverage gaps. From this point the guard triggers reject writes without actor context, so un-upgraded API
   instances, CLIs and jobs fail closed. This is an availability impact, not a security bypass. No separate fencing
   protocol or mixed-mode fallback exists.
4. **Deploy:** deploy the API and BFF with runtime credentials. Resource grants start empty, so system-scoped writes
   are denied and never auto-elevated from `catalog_editor` or `tenant_admin`.
5. **Provision:** the authenticated operator applies an approved manifest of individual grants with the provisioning
   CLI. The manifest is validated against current identities, active memberships, targets and duplicates, and is
   applied in a single transaction.
6. **Verify:** check allowed and denied OIDC users, historical reads and exports, and unchanged library operations.
7. **Rollback:** restore the pre-migration backup. Downgrading to unprotected writers on migrated data is not
   supported.

## Consequences and boundaries

**Benefits:**

- real per-resource backend authorization;
- one meaningful, race-safe personal SoD guarantee;
- legitimate self-assessment;
- an OSCAL-valid, portable type annotation;
- fail-closed provenance capture for all writers;
- least-privilege database roles;
- the same policy in demo and OIDC modes.

**Costs and limits:**

- grant, journal, head and decision tables;
- guard and capture triggers;
- three database roles and the corresponding deployment changes;
- serialization of all writes within one System;
- CLI-only provisioning per System and AP version;
- type-aware import and export;
- multi-session PostgreSQL tests.

System-wide SoD excludes people whose work was unrelated to the reviewed controls. Repeated unconfirmed assignments
can temporarily block `verified` (they are attributable and can be declined).

**Explicitly deferred:**

- grant-management UI, four-eyes approvals, delegated or expiring grants;
- organizational or third-party independence;
- control-scoped SoD;
- general policy engine or event sourcing;
- AR review or approval workflows;
- Finding/POA&M closure;
- dynamic compliance evaluation;
- external tamper-evident audit;
- independent import provenance.

A self-assessment may inform remediation but must not be presented as independent verification.

## Acceptance criteria (required evidence)

All database criteria run on the real PostgreSQL harness (`TEST_DATABASE_URL` targeting a `_test` database), with
business operations executed as `oscal_runtime`. Concurrency tests use independent sessions synchronized with
barriers or advisory locks and bounded lock timeouts. They assert final rows, positions, events, grants, snapshots and
decisions, not merely the absence of deadlock.

1. **Authorization matrix (positive and negative).** For every row of §3, exercised through REST, direct service, CLI
   and nested seed:
   - a viewer holding the required resource grant succeeds without `catalog:write`;
   - `tenant_admin` and `catalog_editor` without it get 403;
   - wrong tenant, same-tenant wrong System/AP/version, and a generic `/implementations/{id}` edit of a bound
     implementation without `system:implement` are denied;
   - first binding without `catalog:write` is denied.
2. **No self-authorization.** A planner cannot issue grants or write ARs. The API role cannot INSERT into
   `resource_grants`. The provisioning CLI rejects missing, invalid or non-allowlisted operator tokens, any supplied
   grantor, a self-grant, a technical beneficiary and a wrong tenant. A revoked grant is never reactivated; manifest
   replay does not recreate it. The issuer and revoker are recorded.
3. **Version-bound grants.** A grant on V1 allows AR work on V1 and denies AR create, edit, import and publish on V2
   until a V2 grant is issued. Revoking the V1 grant denies further V1 work while leaving earlier versions and
   determinations unchanged.
4. **Separate paths.** A conflicted implementer with an assessor grant and `system:self_assess` publishes self and
   legacy ARs without a badge; removing either grant denies. Independent publication requires a typed pin and
   `verified`. No grant or import changes a type.
5. **Conflict detection.** There is one clean `verified` publication. Separate `conflict` negatives cover System
   boundary/status edits, component create/adopt/change, bound implementation edits, pre-binding edits of a later
   bound implementation, binding, association attach/remove, SSP edits, confirmed and self-assigned
   responsibilities, an unrelated control in the same System, an earlier AR contributor whose grant was revoked,
   reverted AP edits before V1, and a publisher with implementation activity. A V2-only AP editor does not affect V1.
6. **Unconfirmed assignments.** A third-party assignment yields `unverifiable` while active. After removal or the
   assignee's decline, the next publication is `verified`. After confirmation it is permanently `conflict`. A
   role-only responsibility has no effect. Only the assignee can confirm.
7. **Unknown stays unknown.** `verified` is denied for a `legacy_gap` System, a bound `provenance_complete = false`
   implementation, `ambiguous` or `technical` actors, and import provenance. Removal, reseed, revocation and later
   markers do not clear these conditions.
8. **Fail-closed journal.** Each protected-table write without actor context fails. This is tested with raw SQL as
   `oscal_runtime`, a simulated old-version service path, the CLI and a seed savepoint. Bookkeeping-only and no-op
   updates create no event. A failure injected after the mutation and before the snapshot or decision leaves no
   event, snapshot or decision. `oscal_runtime` cannot UPDATE, DELETE or TRUNCATE events, versions, decisions or grant
   history, and cannot disable triggers.
9. **Invariants.** Each rule in §9 rejects crossed same-tenant IDs, rebinding, type change and post-activation legacy
   inserts. The migration fails on preflight violations.
10. **Concurrency (both commit orders each).** Cover:
    - conflicting implementation edit vs independent publication;
    - unbound edit vs binding (restart path);
    - grant revocation vs publication;
    - membership deactivation vs publication;
    - unconfirmed assignment vs publication;
    - two parallel publications of the same AR (one creates, one reuses or gets stale);
    - parallel writes to two Systems sharing a catalog revision.

    Assert gapless, commit-ordered positions per System, determinations consistent with the visible history, and no
    unhandled deadlocks. Retried deadlocks are counted and reported. ADR 0022 stale and idempotent responses are
    preserved.
11. **Publication and idempotence.** `published_by` and `document_sha256` are present on new SSP/AP/AR versions and
    NULL publishers are kept for legacy rows. An A→B→A digest hit is reused without a new event, determination or
    token change. A now-conflicted request with an existing digest is denied. A different authorized caller receives
    the original publisher and determination.
12. **OSCAL and import.** Typed AP/AR candidates and exports contain exactly one matching property and pass Trestle,
    official 1.2.1 schema validation and application checks; legacy outputs are untyped. Historical exports are
    unchanged. Import cases: absent, matching, contradictory, duplicate, malformed and foreign properties; legacy pin
    with a property; `independence_claimed` pin rejected. The ADR 0023 replay contract, unauthorized replay and the
    uniqueness-race retry are tested.
13. **Identity and demo.** Technical identities cannot authenticate or be resolved from OIDC. The seed rejects
    `--actor-id` and tenants outside its allowlist. Two real browser sessions switch personas independently with
    correct backend allow/deny decisions and attribution. Cross-site switches, tampered cookies, unknown personas,
    persona keys in OIDC mode and secret fallbacks are rejected. Existing seed history is unchanged.
14. **OIDC transition.** Run the preflight report and migration from a legacy-state database. An un-upgraded writer
    fails after migration. There are no grants before provisioning. Manifest apply and replay work; inactive or
    changed membership after preflight and an unauthorized operator are rejected. Later provisioning works for a new
    AP version. Legitimate actions are confirmed through the GUI without tenant elevation.
15. **Reporting.** Report exact commands, exit codes and passed/failed/skipped counts, plus representative GUI
    results. Skipped required cases are not acceptance evidence.

## Implementation guidance (not implementation approval)

1. Database roles, actor kinds, actor-context helper, guard and capture triggers, journal heads, coverage flags and
   §9 invariants, with all writers (API, CLI, seed) setting context.
2. Resource grants, provisioning CLI with operator authentication, shared in-transaction policy, lock-order
   refactoring and the available-actions endpoint.
3. Immutable AP type, version-bound assessor grants, OSCAL property emission and the narrowed import changes.
4. SOD-ALPHA-01 v1 evaluation, determinations, publication and idempotence behaviour, plus the concurrency tests.
5. Demo personas, BFF switching and OIDC transition tooling, then GUI verification.

Slices are planning aids, not independently accepted security milestones. SoD must not be advertised until all
criteria pass together.

## Related decisions

- Accepted: ADR 0006, 0007, 0015 (amended in §12), 0017, 0019, 0020, 0022, 0023 (import subset amended in §5).
- Proposed: ADR 0024 (Compliance Explorer projection), ADR 0026 (Alpha UI). Draft ADRs on Finding closure are not
  part of this repository and do not affect this decision.
- NIST OSCAL 1.2.1 Assessment Plan and Assessment Results JSON references.

## PO decisions outstanding

- **D1:** An active unconfirmed third-party assignment makes the result `unverifiable` (not `conflict`); decline or
  removal clears it; confirmation is permanent; role-only responsibilities have no effect (§6).
- **D2:** v1 counts every effective content write to System-scoped artifacts, including System boundary/status and
  SSP title edits, but not version publication without content change. This supersedes the earlier provisional
  field-level exceptions in favour of a simpler conservative rule (§6).
- **D3:** Native AR import against `independence_claimed` pins is rejected in Alpha (§5).
- **D4:** The three-role database deployment, including Compose changes, is accepted for Alpha (§8).
- **D5:** CLI-only provisioning per System and per AP version is accepted as an Alpha limitation (§2).

Architect review of §7–§10 and PO acceptance remain outstanding. No implementation is authorized by this proposal.

