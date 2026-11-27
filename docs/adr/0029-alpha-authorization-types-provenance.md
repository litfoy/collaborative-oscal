# ADR 0029: Resource Authorization, Assessment Types, Provenance, and Personal SoD for Alpha

- Status: Approved
- Date: 2026-11-24 (revision 4; incorporates PO/architect decisions D1–D12 and the final independent review corrections)
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
3. Every newly created AP has an immutable `self_assessment` or `independence_claimed` type, exported as a namespaced OSCAL
   property (§4, §5).
4. SOD-ALPHA-01 v1 is a conservative, system-wide personal conflict check, evaluated at each independent AR
   publication with results `verified`, `conflict` or `unverifiable` (§6).
5. PostgreSQL captures effective protected changes atomically, attributed to the actor asserted by the trusted writer (§7–8).
6. Separate database roles distinguish schema ownership, runtime writes and grant provisioning (§8).
7. Supported commands serialize relevant work through one installation-wide transaction gate. Constraints,
   per-System positions and immutable decision evidence remain database protections, not effects of the gate (§9–10).

## 1. Authentication, authorization and OSCAL responsibility

- OIDC and demo authentication both resolve to a trusted internal actor and an active tenant membership. Both use
  the same resource authorization policy and enforcement path. There is no separate demo policy.
- The service receives its principal from the authentication adapter only — never from a caller-selected user ID,
  tenant header, role claim, OSCAL party or CLI argument.
- Authorization is re-evaluated in the **same SQLAlchemy session and PostgreSQL transaction** as the mutation, with
  the gate in §10. Route dependencies may reject early but cannot authorize. BFF affordances are hints (§12).
- Deny by default. Every lookup is tenant-qualified. A request's system ID never routes an unrelated record.
- OSCAL parties, roles, `responsible-parties` and `responsible-roles` remain documentary. An internal-user-to-party
  association may be kept, but it never grants API access. Governance disciplines (data protection, information
  security, AI safety) may appear as OSCAL organization parties, not as technical roles.

## 2. Actors, identities and provisioning authority

**Actor kinds.** `user_identities` gains an immutable `actor_kind`:

- `human`: resolved from a configured OIDC issuer or a reserved demo persona.
- `technical`: reserved issuer `urn:collaborative-oscal:technical` and a fixed subject per purpose (for example
  `demo-seed`, `demo-provisioner`). Technical identities cannot authenticate through the API, cannot be resolved from
  an OIDC token or hold resource grants. A checked set containing one cannot qualify as independent. A database
  CHECK ties `actor_kind = 'technical'` to the reserved issuer.

**Controlled initialization (D9).** Remove `--actor-id`, including the local CLI's implicit human actor. Only the
fixed `demo-seed` command may initialize owner-authorized demo tenants and reserved fixture targets. Its positive
list is fixture library/catalog setup, System/component creation and adoption, implementation/SSP authoring and
binding, SSP publication, self-assessment AP/AR creation, editing and publication, and seed markers. No independent
AP/AR work, creation of legacy classifications, human impersonation, personal confirmations or grant writes. This
is command-specific authorization, not authority conferred by technical kind or tenant allowlisting alone.
Keep the atomic multi-System seed and replay markers: nested services inherit its outer transaction (§10).
Apply demo grants separately after seed commit as `demo-provisioner`, never with the seed's runtime credential.

**Identity assurance.** `human` means a non-technical account; it is not proof that a natural person is behind it. A
valid OIDC access token may identify a service account or client-credentials principal (for example ADR 0023
automation). Each human identity therefore has `identity_assurance`: `unattested` (database default for every
OIDC-resolved identity and every pre-existing identity), `distinct` or `ambiguous`. Only an operator holding global
assurance administration may set `distinct`, attesting that the account is the personal account of one natural
person under the installation's IdP contract: tokens for the API audience must not be obtainable through
client-credentials or service accounts for accounts that are attested. Known aliases, replacement accounts or
unresolved issuer transitions are marked `ambiguous`. `unattested` identities may hold grants and do self-assessment
work, but never qualify as independent. Accounts are never joined by e-mail or display name. Assurance is
installation-wide: changes require explicit owner authorization for global assurance administration (an
owner-managed global allowlist), not merely authority to provision one tenant. Use the same gate as publication
(§10); preserve the value used for each checked actor in the determination.

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
  new grant row and a new issuance intent. Persist a tenant-qualified stable manifest entry key, even after
  revocation. Identical replay is a no-op; reject changed payload under the same key. Replay never recreates a
  revoked entry. Inactive membership prevents use; reactivation permits use only if the grant was never revoked.
- **Alpha limitation:** grant provisioning is CLI-only. A System or AP version created in the GUI is unusable for
  system-scoped work until an operator provisions it. There is no grant-management UI.

## 3. Resource capabilities and operation matrix

Resource capabilities are a separate type and never members of the tenant `Permission` enumeration. A resource check
never falls back to `catalog:write`; first binding explicitly needs both authorities. Active tenant membership is
required for human resource use. Technical commands have only the enumerated §2 authorities.

| Capability | Target | Purpose |
|---|---|---|
| `system:implement` | System | Implementation-side authoring |
| `system:plan_assessment` | System | AP authoring and publication |
| `system:self_assess` | System | Additional precondition for self-assessment and legacy AR work |
| `assessment:assessor` | One published AP version | AR work against exactly that pin |

| Operation | Required authority | Notes |
|---|---|---|
| Browse, validate without saving, list or export versions | Existing tenant read policy (`catalog:read`) | No participation; locking validation still takes the gate |
| Catalog import, Profiles, Mapping Collections, Component Definition library | Existing `catalog:write`/`catalog:import` | Library authorship is not system participation |
| Create System | `catalog:write` (pre-resource exception) | Grants no rights on the new System; starts complete coverage (§7) |
| Edit System (characteristics, boundary, status) | `system:implement` | Journaled participation (§6) |
| Create/edit system component; adopt component definition | `system:implement` | |
| Create/edit **unbound** implementation and its responsibilities | `catalog:write` | Resolve actual binding after taking the gate (§10) |
| Edit **bound** implementation or its responsibilities, through any route | `system:implement` on the bound System | Includes the generic `/implementations/{id}` route |
| Create/edit SSP, publish SSP version | `system:implement` on the SSP System | |
| Attach implementation to SSP | `system:implement` on the SSP System; first binding additionally requires `catalog:write` | ADR 0017 baseline, component and organization checks retained |
| Remove SSP association | `system:implement` on the SSP System | Binding stays (write-once) |
| Confirm or decline one's own named responsibility | The named human assignee with active membership | Self-scoped; no grant (§6) |
| Create typed AP, edit AP, publish AP version | `system:plan_assessment` | For `independence_claimed`, a known `conflict` of the acting planner is rejected early |
| Create, edit, import or publish AR, including import replay | `assessment:assessor` on the AR's exact pinned AP version | Self/legacy pins also need `system:self_assess`; independent publication also needs `verified` (§6) |
| Issue or revoke a grant; mark identity assurance | Provisioning authority (§2) | CLI only |
| Tenant and membership administration | Administrative operator CLI (§8) | Gated; `tenant_admin` receives no resource capabilities |
| Resolve identity / refresh display attributes | Trusted identity adapter | Non-locking lookup; insert or display-attribute update only when needed, outside the gate (§10); not membership or assurance authority |
| Initialize demo fixtures / apply demo grants | Separate technical commands and credentials (§2) | No human grants |

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

**Assignment lifecycle (D1).** Diff assignments; do not replace unchanged siblings. Each ID fixes tenant,
implementation, kind, role and optional assignee; substitution means remove + new ID. Third-party personal
assignment starts pending; human self-assignment starts confirmed. Only the named active human may move pending
to confirmed or declined. Neither state resets. Removal ends any assignment; reassignment has a fresh ID. Role-only
has no personal state. New named assignments require active membership; retaining an unchanged inactive assignee
does not block other edits. Confirm/decline requires the implementation's expected token; one effective command
advances it once. Repeating an unchanged decision creates no participation. Adding/removing a named assignment
is an edit by its author, not work by a pending assignee. Role-only transitions have no personal SoD effect;
decline is recorded but is not implementation participation by the decliner.

While an actor in the checked set is the named assignee of an active,
unconfirmed responsibility on an implementation bound to S, the result is `unverifiable`, not `conflict`. Removal or
the assignee's own decline clears this effect, because no personal participation was ever recorded. A third party
therefore cannot permanently disqualify an assessor. Confirmation is permanent participation. Assignments, decisions
to confirm or decline, and their actors are journaled separately.

**Checked actor set** for a new version of an AR pinned to AP version V:

- (a) the AP-side actor set stored immutably at V's original publication: the AP creator, every actor with an
  effective AP edit before that publication, including reverted edits, and V's original publisher. Later AP editors
  and publishers of reused digests never join V's set.
- (b) the AR creator, the import submitter and every actor with an effective AR edit through this request, including
  actors whose grants were later revoked.
- (c) the requesting publisher.

An unused grant or a documentary party is not assessment work. Publication is not implementation activity, but
the AP version publisher and the AR publisher are checked actors under (a) and (c).

**Result.** Evaluated over System S's journal through the cut-off (§10):

| Result | Meaning | Independent AR publication |
|---|---|---|
| `conflict` | A checked actor has recorded personal implementation activity on S | Denied |
| `unverifiable` | Coverage of S is incomplete (legacy start, bound pre-instrumentation implementation, recorded gap); a checked actor is `technical`, `unattested` or `ambiguous`; an active unconfirmed assignment names a checked actor; or the AR carries import provenance | Denied |
| `verified` | Coverage is complete to the cut-off and none of the above applies | Permitted if all other checks pass |

`conflict` takes precedence over `unverifiable`. Missing history never yields `verified`.

`verified` means only that the recorded personal-conflict test passed for recorded internal actors. It does not
certify organizational independence, absence of collusion or aliases, off-platform collaboration, competence,
correctness of findings, or any review or approval. UI and reports use wording such as “Personal independence check
passed (recorded history)”. In demo mode they add “demo accounts”.

The same rule evaluates early rejections: independent AP creation, edit or version publication by a conflicted
planner, and assessor issuance. The decisive evaluation is repeated on every independent AR publish request. Self-assessment and legacy
paths do not evaluate it.

**Determination record.** Each newly published independent AR version stores exactly one immutable determination:

- result `verified` and rule `SOD-ALPHA-01 v1`;
- System, cut-off position and coverage origin;
- checked actor IDs with their kinds and assurance as evaluated, including former contributors;
- AP version, new AR version and publisher;
- server time and authentication mode.

Record the complete-coverage and no-blocking-assignment basis at that cut-off. No self/legacy version has a
determination. Later mutations never change it; reuse returns it unchanged (§10).

## 7. Database-enforced participation journal (fail closed)

This is a minimal participation log, not event sourcing. Current state stays in existing tables and is never rebuilt
from events.

**Actor context.** Every protected transaction runs `SET LOCAL` for `collaborative_oscal.actor_id`,
`collaborative_oscal.tenant_id` and `collaborative_oscal.operation` through one shared helper. This applies to API,
CLI, seed and nested savepoint writers alike.

**Guard triggers.** BEFORE INSERT/UPDATE/DELETE triggers on the protected tables raise an error when:

- context is missing, empty or malformed;
- the actor is unknown;
- the context tenant differs from OLD on delete, NEW on insert or either on update;
- a `human` actor lacks an active membership in that tenant;
- a `technical` actor writes outside its owner-managed tenant allowlist.

Protected tables: `information_systems`, `system_components`, `control_implementations`,
`implementation_responsibilities`, `system_security_plans`, `system_security_plan_implementations`,
`assessment_plans`, `assessment_results`, the three `*_versions` tables and `resource_grants`. The determination
is protected within the immutable AR version (§9). Administrative writes use the restricted interfaces in §8.

Code that does not set the context — including pre-cut-over API instances, old CLIs and forgotten paths — therefore
fails closed. The guard is completeness and defence in depth; authorization remains the service's job (§1).

**Capture triggers.** AFTER ROW triggers, `SECURITY DEFINER` and owned by `oscal_owner` with a fixed `search_path`,
append facts in the same transaction according to the following routing contract. Capture structural changes, not
the service's interpretation of them. Each event records:

- tenant, System (nullable) and implementation (nullable);
- subject table, row ID and operation;
- changed content columns;
- actor, actor kind and operation label;
- for responsibilities: stable assignment ID, assignee, kind, role and old/new decision state;
- `clock_timestamp()`.

| Mutation | Durable route and captured fact |
|---|---|
| System / component / SSP create or edit | NEW tenant and immutable System key, distinct content columns; adoption records the component write, not library authorship. |
| Implementation create/edit | Stable tenant and implementation ID; no System until bound. On first NULL→S record the unique binding and its System position. Component completion within S is an edit, not a second binding. |
| Assignment create, confirm, decline, remove | Route through the retained implementation. Compare OLD/NEW transition; deletion uses OLD. Record the actual actor separately from the assignee. Never infer assent from assignment by someone else. |
| SSP attach/detach | Association contains tenant, System, SSP and implementation; capture INSERT from NEW and DELETE from OLD. Removing it never removes binding, participation or a gap. |
| AP/AR draft create, import or edit | Route by immutable System and parent pin. Record creator, actual submitter and effective editors; a reverted edit remains participation. Import replay is not an edit. |
| SSP/AP/AR version insert | Resolve immutable parent to System and version ID. This insert's capture produces the **one authoritative publication event** for that version. Neither token update nor decision produces another. |
| Grant issuance/revocation | Resolve exact System or AP version to tenant/System; administrative fact, not personal work. Library, membership and assurance writes take the gate but are not System content edits. |

Compare actual content null-safely (including JSON values), not the UPDATE column list. Exclude bookkeeping-only
`updated_at`, `updated_by`, `concurrency_version`, validation and ineffective writes. Classify new columns explicitly
when changing schema. The versioned §6 classifier consumes these facts, not free-form operation labels. Do not keep
complete old/new documents or reconstruct historical state. Disallow unsupported protected deletes, cascades,
identity reuse and reparenting; retain assignment identity on removal (tombstone or immutable removal fact).

**Positions and coverage.**

- Inserting a System creates its `system_journal_heads` row (`last_position`, `coverage_origin = complete`) and a
  creation event at position 1.
- An event with a System takes the next position by updating that head row. The head row lock is held to commit, so
  positions are gapless and follow commit order within a System. A unique index on `(system_id, position)` enforces
  this.
- Events on unbound implementations have no System position. Retain them by immutable tenant/implementation ID;
  a cut-off includes them **iff** the durable first-binding position is at or before it, never by a current SSP join.
- The database supplies the immutable `provenance_complete` flag: true when inserted after activation, false for
  pre-existing rows.
- **Binding** (write-once `system_id` NULL→S) records a binding event at a System position. Earlier unbound events
  count from that position onward. If `provenance_complete = false`, that same binding fact marks a permanent
  coverage gap effective at the binding position; no cut-off can include the binding but exclude its gap.
- Nothing — removal, reseed, revocation, a later marker or a fresh System — clears a gap or recorded participation.
- Pre-existing Systems receive `coverage_origin = legacy_gap` and can never yield `verified` in Alpha.

**Publication facts.** New SSP/AP/AR version rows get:

- `published_by`, filled by trigger from the actor context and NOT NULL for new rows. Legacy rows stay NULL; no
  publishers are invented.
- `document_sha256`: hash the final Trestle-serialized JSON value that is stored, with UUID, version and last-modified
  intact. Use `packages/oscal`'s `canonical_json_sha256`: recursively sorted object keys, preserved array order,
  compact comma/colon separators, unescaped Unicode, no NaN/infinity, UTF-8, SHA-256 hex. Recompute on JSON
  read-back for verification; neither transmitted bytes nor PostgreSQL's JSONB display text is the input.
  This is a content identifier, not a signature or proof of independence.

The existing normalized `content_sha256` stays for deduplication only. Typed AP versions additionally store their
immutable AP-side actor set (§6 (a)); legacy contributors are unknown, never presented as a complete set.

## 8. Database trust boundary and privileges

**Three guarantees (D6).** Trusted adapters authenticate the actor; trusted application services authorize commands
and evaluate SoD. PostgreSQL enforces structural integrity, atomic capture and protected history. A transaction-local
setting is a trusted assertion, not independent evidence of a token or person. Runtime credentials can assert a false
actor or submit a structurally valid but dishonest decision. Provisioner credentials can likewise assert an allowed
operator without proving token validation. Neither credential is supported for ad hoc SQL. Owners, infrastructure
administrators, superusers and backup operators are trusted. This is not external tamper evidence.

| Effective role | Positive operations | Exclusions |
|---|---|---|
| `oscal_owner` | Own schema, tables, sequences and functions; install triggers via Alembic; maintain allowlists, reserved identities and administrative bootstrap. Online membership/allowlist administration participates in §10. | No owner credentials in API, BFF, seed or provisioning CLI. |
| `oscal_runtime` | Tenant-qualified business reads (including version list/export, digest lookup and RETURNING); only required working-table DML and supported deletes; INSERT new versions with decision basis where applicable. Human identity upsert permits identity keys on INSERT and display/email/timestamp on conflict UPDATE. | No membership/grant/allowlist administration, reserved identity insertion, identity key/kind/assurance changes, direct journal/head writes, version UPDATE/DELETE or caller-defined coverage/publisher. |
| `oscal_provisioner` | Resolve the authenticated operator by existing issuer/subject; read exact memberships, grants and targets. Execute only scoped issue/revoke and assurance procedures; grant operations check allowlist, shape and beneficiary and stamp context actor. | No arbitrary grant INSERT/UPDATE/DELETE, business DML, human impersonation through CLI inputs, membership or allowlist administration. |

Both business roles can take the gate. Provide tenant-qualified read interfaces for journal facts, binding, coverage,
heads, eligibility inputs and permitted allowlist checks; no direct journal/head access. Grant/membership checks
use ordinary SELECT **after the gate**, not locking SELECT needing UPDATE privileges. Supply SELECT/UPDATE for
remaining working-row locks only where independently needed; otherwise remove the lock or use a narrow fixed-query
interface. Never broaden grants on read-only sources just to allow `FOR UPDATE`. Administrative bootstrap is a
separate credential/job, not an API membership upsert. Restrict runtime identity INSERT columns/defaults and
enforce immutable issuer/subject and the reserved issuer/kind pairing in the database.

Grant CONNECT and schema USAGE, not CREATE in any trusted schema. Grant sequence USAGE only for actual generated
keys. No table-wide privilege defeats column limits. Audit effective privileges via PUBLIC, inheritance, assumable
roles and grant options: neither business role owns objects, can assume the owner/other credential, administer roles,
disable triggers, bypass replication triggers, TRUNCATE protected tables or replace functions. Owner-defined capture,
read and provision routines use qualified objects, fixed trusted `search_path` with `pg_temp` last, and no dynamic
caller SQL. Revoke default PUBLIC EXECUTE; grant only required entry points, never internal trigger helpers. Apply
ACLs to existing objects and default privileges for future objects of the actual creating owner. Separate secrets,
connections, mounts and jobs in Compose, development, Alembic, CLI and tests (§13).

## 9. Relational invariants

Composite FKs (with the supporting unique keys where missing), CHECKs or triggers enforce:

1. AP: `(tenant, ssp_id, system_id)` → SSP; `(tenant, ssp_id, ssp_version_id)` → SSP version. The SSP version's
   catalog/revision must match its SSP baseline. Provide exact non-partial parent unique keys for all composite FKs.
2. AP version: `(tenant, ap_id, ssp_version_id, assessment_type)` → AP.
3. AR: `(tenant, ap_id, system_id)` → AP; `(tenant, ap_id, ap_version_id)` → AP version.
4. AR version: `(tenant, ar_id, ap_version_id)` → AR. Keep AR import source identity, digest and submission facts
   immutable after creation; retain the ADR 0023 tenant/source UUID unique key and completeness check.
5. Implementation `system_id` and `system_component_id` each permit NULL→value once, never clearing or substitution.
   Component requires matching System. Preserve tenant/context FKs and ADR 0017 baseline/organization checks;
   binding does not require a continuing SSP association. Stable subject IDs and tenant cannot move.
6. AP type: closed, non-null, immutable and non-legacy for new APs after activation. A new version of an existing
   legacy AP must copy its legacy type; it is not a new AP.
7. Grants: capability-to-target shape CHECK; `(tenant, system_id)` → System; `(tenant, ap_id, ap_version_id)` → AP
   version; `(tenant, beneficiary)` → membership; grantor ≠ beneficiary. Require the selected target columns non-null
   and all alternatives null; separate active unique indexes per target shape include tenant/capability/beneficiary.
   Issuance checks active human membership under the gate. Target, grantor and beneficiary are immutable; revocation
   changes only active→revoked with actor/time together, never deletion or clearing. Preserve manifest identity (§2).
8. Responsibility assignee `(tenant, user_id)` → membership. Enforce §6 transitions for INSERT as well as UPDATE,
   including actor match, no technical confirmation, no personal state for role-only and NULL-safe uniqueness of
   active logical assignments. A removed assignment's ID cannot be reused.
9. Co-locate the determination with the immutable AR version (one set of decision fields, not a second mutable
   aggregate). Constrain the version's relational type to the exact AP pin by composite FK. Require a complete
   `verified` basis (§6) for independent type, absent for self/legacy, with explicit non-null checks; a unique FK
   alone cannot require presence. Derive tenant/System/AP and publisher from the version chain and stamped publisher,
   not independently supplied IDs. Validate the basis shape, distinct checked IDs with frozen assurance values,
   rule, mode and cut-off against this System's head at insert. The service, not a CHECK, establishes policy truth.

Preflight reports current violations and fails rather than auto-repairing. Current rows cannot establish past
binding transitions, contributors or publishers. The immutable publication guard applies to metadata as well as JSON.

## 10. Command transaction, installation gate and publication

**Supported writer contract (D7).** One installation uses one PostgreSQL application database. Reserve the single
bigint advisory key **8188815197680786** (the existing demo seed key) as its installation-wide write gate. Every
participating transaction takes `pg_advisory_xact_lock` on that exact key, on its business connection, before any
conflicting lock, DML, flush or decision read. Never use a process mutex, session lock, per-tenant key or second
seed lock. The gate spans all Systems, tenants and shared resources until outer commit/rollback.

Participants include REST/direct-service writes, business and administrative CLIs, seeds, provisioning, grant
replay/revocation, global identity assurance, membership/role and allowlist changes,
catalog/profile/mapping/component-library writers and any validator/reader using locking SELECT.
Treat FK checks, catalog-revision triggers, unique indexes and ORM autoflush as lock takers too. Pure non-locking
reads remain parallel; a read path may instead stop taking unnecessary row locks. The BFF does not take the gate.
Identity resolution is not a participant: it uses a non-locking lookup by issuer/subject and inserts a missing
identity or updates changed display attributes in a short, ungated transaction. Display attributes are not SoD
inputs; issuer, subject, kind and assurance are immutable to the runtime role, and a new identity cannot be in a
checked set. Commands re-read kind, assurance and membership under the gate.
The gate is **cooperative**: arbitrary SQL need not honor it. It does not replace constraints, ACLs, guards, head
updates or token checks, nor make administrative/DDL deadlocks impossible. Inventory and test entry points;
unsupported direct writes are not covered by the serialization claim. Maintenance instead fences all writers (§13).

**Command ownership (D8).** Use a small application command boundary, not a general transaction framework:

1. Authenticate via the appropriate adapter; perform external I/O and input-only checks outside the gate. Start a
   fresh READ COMMITTED Session/transaction with no pending objects. Acquire the gate as a separate first database
   statement with autoflush suppressed. Use only the stable identity ID from identity resolution; never use pre-gate
   ORM objects or a route's tenant decision as authoritative.
2. Before any protected flush, set actor/tenant/operation on this connection using parameterized transaction-local
   settings (§7). No session defaults. Resolve actual resource/pin and re-read membership, grants, assurance,
   bindings and relevant journal facts in subsequent statements. Authorize, then check the **original** ADR 0022
   expected token(s), including both on binding. Refresh/expire previously loaded rows after waits; do not trust the
   identity map. No-op/stale semantics, mapper checks and 409 responses remain; positions do not bump System tokens.
3. Nested services inherit the outer principal, tenant, connection and gate; no independent commit or new engine.
   Savepoints may isolate local work, not switch principals. Set context before savepoint creation can flush;
   explicitly restore operation labels on successful release, and on rollback use the restored outer context.
   Only the boundary commits. Rollback removes changes, positions and versions together. Pool check-in must leave
   no open transaction or actor defaults; initialize context afresh on every checkout/transaction.
4. Bound acquisition time, transaction duration, batch sizes and retry count. Keep network calls/user interaction
   outside. On a known rollback from deadlock/serialization failure, retry the whole command with a fresh Session,
   gate, authorization and unchanged expected tokens. Never retry a stale response, denial, validation failure or
   uncertain commit as success. A source-UUID uniqueness recovery is a fresh gated, reauthorized ADR 0023 lookup,
   not an unconditional insert retry. Expose exhaustion; record waits and retries before considering finer locks.

**Cut-off.** Flush earlier effective writes in the command before evaluating. Under the gate the System head now
includes committed history and any preceding events of this same transaction. Evaluate through that position with
the requesting publisher; exclude the publication's own event. The immutable version insert captures that next
position, its publisher and determination in one commit. Missing head or incomplete evidence cannot yield `verified`.

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
- Historical SSP/AP/AR snapshot values are never updated, and their exports are generated from those unchanged
  stored values. Stored JSONB does not preserve original serialized bytes (key order, whitespace); "unchanged" means
  an equal `canonical_json_sha256` before and after migration. No type properties, publishers or contributors are
  backfilled; legacy `document_sha256` stays NULL.
- Pre-existing Systems are `legacy_gap`, and pre-existing implementations are `provenance_complete = false`. History
  before activation is unknown, not conflict-free.
- Pre-existing identities are `unattested` (§2) until explicitly attested.
- Existing seed history is not reassigned. The Alpha showcase uses a newly created, fully covered System.
- An attributable operator attestation of earlier history is out of scope for Alpha.

## 12. UI available actions and demo personas

**Available actions.** A read-only endpoint, for example `GET /tenants/{tenant_id}/available-actions?resource_type=…&resource_id=…`,
returns the actions the current actor may attempt on one resource. It is computed by the same policy, including an
SoD pre-check for independent AR publication. For the current actor it returns reason codes such as `missing_grant`,
`sod_conflict` or `sod_unverifiable`. These are hints only. The BFF replaces its `catalog:write`-based write
affordances with this endpoint for system-scoped resources.

**Demo personas.** Seven to ten reserved fictional `human` identities with fixed memberships and roles, seeded as
`distinct` (fictional accounts; determinations record `auth_mode = demo`), and grants applied from the checked-in demo
manifest by `demo-provisioner`.

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
3. a separate technical provisioning command may apply the demo grant manifest after initialization.

ADR 0015's loopback, protected-network, dedicated-database and server-only-secret constraints remain. Demo mode still
provides no per-person accountability: it demonstrates different accounts, not different humans. Determinations made
in demo mode record `auth_mode = demo`.

## 13. Coordinated installation and OIDC transition (D12)

1. Inventory current identities, memberships, pins, baselines, legacy data and detectable §9 violations. Schedule
   downtime. Stop API, CLIs, seed and operator jobs; block reconnects and drain/terminate old privileged sessions.
   The advisory gate is not a fence against old binaries. Take and verify a restorable final backup; repeat preflight
   under the maintenance fence. Abort on inconsistent data rather than invent history.
2. Bootstrap the three roles, transfer existing object ownership and install effective/default ACLs. Separate owner
   migration/bootstrap, runtime/seed and provisioner jobs and secrets; the BFF has no DB credential. Withdraw old
   privileged credentials and access paths, including shared mounts. Verify effective roles on actual connections.
3. As owner prepare additive schema and exact parent keys, classify legacy APs and pins in relational metadata,
   mark old Systems/implementations incomplete, existing identities `unattested` and existing personal assignments
   unconfirmed (not inferred assent).
   Historical actor sets are unknown, not empty. No historical JSON rewrite or synthetic participation. Validate
   constraints and install protected reads, immutable metadata, guard/capture and coverage initialization before
   reopening. Schema preparation is **not** the start of complete coverage.
4. Deploy only compatible gated writers, including operator and seed tools. Activate authorization and capture
   together. Grants start empty; no tenant-role elevation. Apply authorized tenant manifests in bounded atomic
   commands after checking current targets and memberships. Only Systems created under active protection can start
   complete. Never bridge an unprotected interval. Independent publication stays disabled until its full contract
   is implemented, independently verified against the acceptance criteria and explicitly accepted.
5. **Go/no-go before reopening:** verify allow/deny paths, old credential rejection, historical exports and library
   operations on clean and upgraded installations. Before release to users, rollback means restore the fenced
   backup and compatible deployment/credentials in isolation. After live writes resume, restore would lose them:
   stop writes and obtain an explicit recovery/data-loss decision. No downgrade to unprotected writers on live data.

## Consequences and boundaries

**Benefits:**

- real per-resource backend authorization;
- one personal SoD decision serialized with supported writers;
- legitimate self-assessment;
- an OSCAL-valid, portable type annotation;
- database-enforced capture of effective protected DML within the stated trust boundary;
- least-privilege database roles;
- the same policy in demo and OIDC modes.

**Costs and limits:**

- grant, journal and head tables and immutable version/decision metadata;
- guard and capture triggers;
- three database roles and the corresponding deployment changes;
- installation-wide write contention, including locking reads; accepted for Alpha, with bounded commands;
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

After full acceptance, independent human review and preferably human-led consolidation/major refactoring under an
experienced Python developer with OSCAL expertise are intended. Do not anticipate that work or add Beta architecture.
Defer finer write serialization until measured contention justifies it; control-scoped and organizational SoD stay deferred.

## Acceptance criteria (required evidence)

Use real PostgreSQL, one `_test` database and separate credentials/connections: owner for migration/setup, runtime
for business/seed, provisioner for provisioning. Assert effective role, ownership and inherited/assumable privileges;
owner-run business tests do not count. Synchronize independent transactions with barriers and bounded timeouts.
Assert final rows, positions, grants, snapshots and decision evidence, not merely absence of deadlock.

1. **Authorization matrix (positive and negative).** Exercise every §3 row through its supported entry points,
   covering REST, direct service, CLI and nested seed. For human resource writes:
   - a viewer holding the required resource grant succeeds without `catalog:write`;
   - `tenant_admin` and `catalog_editor` without it get 403;
   - wrong tenant, same-tenant wrong System/AP/version, and a generic `/implementations/{id}` edit of a bound
     implementation without `system:implement` are denied;
   - first binding without `catalog:write` is denied.
2. **No self-authorization.** A planner grant alone permits neither grant issuance nor AR writes. The API role cannot INSERT into
   `resource_grants`. The provisioning CLI rejects missing, invalid or non-allowlisted operator tokens, any supplied
   grantor, a self-grant, a technical beneficiary and a wrong tenant. A revoked grant is never reactivated; manifest
   replay does not recreate it. The issuer and revoker are recorded. Test changed manifest payload, explicit reissue,
   NULL target shapes, duplicate active targets, denial of direct provisioner DML and unauthorized assurance changes.
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
   reverted AP edits before V1, an AP V1 publisher without AP edits who later confirms a responsibility or edits the
   System, and an AR publisher with implementation activity. A V2-only AP editor does not affect V1.
6. **Unconfirmed assignments.** A third-party assignment yields `unverifiable` while active. After removal or the
   assignee's decline, the next publication is `verified`. After confirmation it is permanently `conflict`. A
   role-only responsibility has no personal effect. Only the assignee can confirm/decline. Change a sibling and
   verify stable ID/state/token behavior; reject assignee substitution, resetting a decision and duplicate role-only rows.
7. **Unknown stays unknown.** `verified` is denied for a `legacy_gap` System, a bound `provenance_complete = false`
   implementation, `unattested`, `ambiguous` or `technical` actors, and import provenance. New OIDC identities and
   migrated identities are `unattested`; only a global assurance administrator can set `distinct`. Removal, reseed,
   revocation and later
   markers never clear a historical gap or confirmed participation. Compare cut-offs before/after binding, including
   detach and attempted delete/reinsert; do not rewrite earlier decisions when assurance changes.
8. **Fail-closed journal.** Each protected-table write without actor context fails. This is tested with raw SQL as
   `oscal_runtime`, a simulated old-version service path, the CLI and a seed savepoint. Bookkeeping-only and no-op
   updates create no event. A failure injected after the mutation and before the snapshot or decision leaves no
   event, snapshot or decision. `oscal_runtime` cannot UPDATE, DELETE or TRUNCATE events, versions, decisions or grant
   history, and cannot disable triggers. Test invalid/empty context, OLD tenant on removal, pool reuse after commit
   and rollback, autoflush, released/rolled-back savepoints and restored sibling labels. Exercise permitted identity
   upsert, reads/export, gate, publish and provision; deny owner assumption, trigger/function replacement, reserved
   identity insertion, allowlist and protected-column writes. Valid context does not independently authenticate raw SQL.
9. **Invariants.** Each rule in §9 rejects crossed same-tenant IDs, rebinding, type change and post-activation legacy
   AP inserts. Test SSP baseline mismatch, immutable import provenance, old AP publishing a legacy version, and
   rejection of missing, duplicate, malformed, wrong-pin or self/legacy determinations. Preflight fails on violations.
10. **Concurrency (both commit orders each).** Cover:
    - conflicting implementation edit vs independent publication;
    - unbound edit vs binding (resolve actual authority after the wait);
    - grant revocation vs publication;
    - membership deactivation vs publication;
    - unconfirmed assignment vs publication;
    - two parallel publications of the same AR (one creates, one reuses or gets stale);
    - two Systems sharing a catalog revision, old/new source replacement, component adoption and locking validation;
    - global assurance change vs publication involving a historical actor; membership/bootstrap,
      provisioning, library CLI and nested seed each wait on the same gate before relevant reads, locks or DML.

    Assert gapless, commit-ordered positions per System, determinations consistent with the visible history, and no
    unhandled deadlocks. Retried deadlocks are counted and reported. ADR 0022 stale and idempotent responses are
    preserved. Use a held gate to verify supported entry points wait and pure reads, including authenticated requests
    with identity resolution, proceed. Check rollback of
    allocated positions, preceding writes in the same transaction, fresh Session/authorization on bounded retries,
    and exhaustion without duplicate effects. The gate is not protection against non-cooperating SQL.
11. **Publication and idempotence.** `published_by` and `document_sha256` are present on new SSP/AP/AR versions and
    NULL publishers are kept for legacy rows. An A→B→A digest hit is reused without a new event, determination or
    token change. A now-conflicted request with an existing digest is denied. A different authorized caller receives
    the original publisher and determination. Recompute the full canonical digest from stored JSON; distinguish it
    from normalized content. Assert one publication event per new version, exactly one frozen independent basis
    (including assurance and cut-off), none on self/legacy; later edits/assurance changes do not alter the evidence.
12. **OSCAL and import.** Typed AP/AR candidates and exports contain exactly one matching property and pass Trestle,
    official 1.2.1 schema validation and application checks; legacy outputs are untyped. Historical exports are
    unchanged (equal canonical digest of the stored value before and after migration). Import cases: absent, matching, contradictory, duplicate, malformed and foreign properties; legacy pin
    with a property; `independence_claimed` pin rejected. The ADR 0023 replay contract, unauthorized replay and the
    uniqueness-race recovery are tested, including reauthorization after rollback, 201/200/409 for authorized users,
    unchanged original submitter and no participation on replay.
13. **Identity and demo.** Technical identities cannot authenticate or be resolved from OIDC. The seed rejects
    `--actor-id` and tenants outside its allowlist. Two real browser sessions switch personas independently with
    correct backend allow/deny decisions and attribution. Cross-site switches, tampered cookies, unknown personas,
    persona keys in OIDC mode and secret fallbacks are rejected. Existing seed history is unchanged. Test atomic
    multi-System seed failure and rerun, allowed self fixtures, denial of non-fixture targets, human confirmation,
    grant writes and independent publication. Apply/replay grants separately with provisioner credentials.
14. **OIDC transition.** Rehearse §13 on a clean install and an existing volume, including backup restore, fencing,
    role ownership/secret isolation, no uncovered writes, rollback decision point and disabled independent publication
    before full verification. Run the preflight report and migration from a legacy-state database. An un-upgraded writer
    fails after migration. There are no grants before provisioning. Manifest apply and replay work; inactive or
    changed membership after preflight and an unauthorized operator are rejected. Later provisioning works for a new
    AP version. Legitimate actions are confirmed through the GUI without tenant elevation.
15. **Reporting.** Report exact commands, exit codes and passed/failed/skipped counts, plus representative GUI
    results. Skipped required cases are not acceptance evidence.

## Implementation guidance (not implementation approval)

1. **Database Security & Provenance Foundation.** Prepare roles/ACLs, separate owner/runtime/provisioner credentials
   for development and tests, separate-role harness, gate/command contract, actor context, stable assignments,
   immutable AP type column with exact pin/type keys, routing, coverage schema, trigger and preflight tests. No
   coverage claim or production guard activation on incompatible writers.
2. **Resource Authorization & Provenance Activation.** Integrate every supported participant, membership/assurance
   administration, explicit grants, authenticated provisioning, technical seed limits, separate Compose jobs and
   secrets, available-actions policy without SoD reason codes and capture. Only `self_assessment` APs can be created;
   `independence_claimed` AP creation is rejected in code (no runtime toggle) until package 4 is accepted. Test
   coherent activation under the maintenance fence; run real concurrency tests from this package.
3. **Assessment Types & OSCAL Interoperability.** Add version-bound assessor checks by type, OSCAL property,
   self/legacy workflows and narrow native import/replay contract.
4. **Personal SoD & Immutable Determinations.** Implement versioned classification, frozen actor sets and assurance,
   early checks, SoD reason codes in available actions, publication cut-off, immutable decision cardinality,
   canonical hash, reuse and contention tests. Enable `independence_claimed` AP creation in code.
5. **Multi-User Demo, Migration & Full Acceptance.** Persona switching, separate technical manifest, clean/upgrade
   rehearsal, credential withdrawal/rollback exercise, GUI and all 15 acceptance criteria together. Independent
   publication is enabled on an installation only after this acceptance.

Packages are sequential development boundaries, not independently deployable releases. §13 controls installation:
prepare schema, activate compatible writers and protection together, then permit independent publication and
advertise verified independence only after full verification and explicit acceptance. No mixed-mode fallback.

## Related decisions

- Accepted: ADR 0006, 0007, 0015 (amended in §12), 0017, 0019, 0020, 0022, 0023 (import subset amended in §5).
- Proposed: ADR 0024 (Compliance Explorer projection), ADR 0026 (Alpha UI). Draft ADRs on Finding closure are not
  part of this repository and do not affect this decision.
- NIST OSCAL 1.2.1 Assessment Plan and Assessment Results JSON references.

## Decision status

D1 personal responsibilities and D2 System-wide SoD (§6), D3 independent import exclusion (§5), D4 role separation
and D6 trust boundary (§8), D5 CLI provisioning and D9 technical fixtures (§2–3), D7 installation serialization and
D8 command ownership (§10), D10 durable participation (§7, §9), D11 immutable publication (§6–7, §9–10) and D12
coordinated activation (§13) are agreed design inputs. Revision 4 applies the final review corrections (identity
attestation, ungated identity resolution, AP publisher in the frozen set, package allocation, snapshot immutability
wording). Revision 4 is **Approved** by explicit PO acceptance. Implementation is authorized package by package;
each milestone requires explicit PO/architect review before the next begins.

