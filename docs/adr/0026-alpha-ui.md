# ADR 0026: Explorer-Centered Frontend Information Architecture and Incremental UX Evolution

- **Status:** Proposed
- **Date:** 2026-11-22

## Context

Collaborative OSCAL is an OSCAL-native, multi-tenant governance application. Its frontend has grown around individual features and document-oriented workflows, including Catalogs, Profiles, Component Definitions, Control Mappings, Information Systems, System Security Plans, Assessment Plans, and Assessment Results. The existing top-level navigation exposes these functions, but does not yet make their relationships or the user's next task sufficiently clear.

Different users approach the same governance information from different directions: a system owner starts with a system; a governance specialist with requirements; a security practitioner with measures and implementations; an assessor with plans, results, and findings. Separate role-specific applications or data models would obscure the intended reuse of shared information while independent assessments remain distinct.

The Compliance Explorer (ADR 0024, currently Proposed) already offers a read-only cross-aggregate projection for one system and explicitly selected Profiles, with Requirements and page-local Measures views. It must not become a second authoritative model or imply compliance conclusions. The frontend redesign must make these relationships easier to understand without weakening the existing domain, security, revision, or concurrency contracts.

## Decision

### 1. Explorer-centered professional application

- Organize the user experience as an **explorer-centered domain application**, not primarily as a collection of OSCAL document editors or an interactive knowledge graph.
- Prefer clear navigation, searchable or filterable lists where supported, detail views, and contextual links to related workflows. An optional graphical relationship view may be considered later; it is not the primary interface.
- Offer four complementary **user-selectable perspectives**: **Systems**, **Requirements**, **Measures**, and **Assessments**. These are different presentations and entry points into the existing domain, not new authoritative aggregates or separate applications.
- A perspective is not a security role. Do not introduce automatic role personalization or new authorization rules as part of this decision. Existing backend-enforced tenant scope and permissions remain authoritative.

### 2. Separate entry point, navigation, exploration, and authoring

- Keep authentication and tenant selection separate from each tenant's workspace experience.
- Within an authorized tenant, use `/t/[tenantId]` as the **workspace overview and entry point**. It presents existing systems and clear paths into the four perspectives and established modeling/library functions. The overview is a replaceable presentation layer, not a new source of business state or compliance evaluations.
- Keep navigation and workspace layout independent of the underlying explorer views and editors. Existing routes remain accessible; UI restructuring must not require changing established document or API identities.
- Group navigation conceptually into **Workspace Overview**, **Explorer**, and **Libraries & Modeling**. A left-hand, responsive navigation is the current design direction, **not a decided layout requirement**; its exact arrangement and behavior require UI-2 design review.
- Make editing available through existing, appropriately authorized workflows reached from the relevant context. Read-only explorer views do not acquire mutation authority merely by offering navigation to an editor.

### 3. Preserve domain distinctions and truthful presentation

- Distinguish reusable **Component Definitions**, concrete **System Components**, and requirement-specific **Control Implementations**; do not merge them into a generic measure object. A Measures perspective may expose both system-specific and reusable resources, with their meaning made explicit.
- Keep Assessment Plans, Assessment Results, and their historical references distinguishable. Shared information must not imply shared findings or assessment conclusions.
- Preserve source Catalog identities, pinned revisions, Profile selection provenance, and the immutability of published OSCAL snapshots.
- Do not infer regulatory applicability, control equivalence, implementation effectiveness, compliance scores, or consolidated assessment verdicts from navigation or explorer projections.
- State scope and completeness limitations where relevant. In particular, ADR 0024's C-light Measures view includes only Controls on the loaded page, not all Controls from every page.

### 4. Incremental evolution using existing technology

- Retain the existing Next.js/React/TypeScript frontend, Browser BFF, API contracts, internationalization approach (ADR 0018), and established styling patterns. This decision authorizes neither a frontend rewrite nor new dependencies, backend models, or API endpoints.
- Evolve the interface in small, independently reviewable increments. Preserve existing functionality, tenant isolation, editor drafts, optimistic-concurrency tokens, conflict handling, publication semantics, and relevant routes.
- Use accessible, responsive interaction patterns, including meaningful headings and landmarks, keyboard operation, visible focus, and understandable navigation labels. Support English and German through the existing localization architecture; user-authored OSCAL content is not translated.
- Avoid unsupported task dashboards, artificial summary metrics, and expensive data-fetch fan-out solely to populate an overview page.

## Implementation and verification notes (non-normative)

- **UI-1 — Workspace Overview:** Implemented in the reviewed 2026-11-21 repository snapshot at `apps/web/src/app/t/[tenantId]/page.tsx`, with root/workspace entry routing, an Overview link, EN/DE labels, and focused tests. This statement describes the inspected snapshot; it is not evidence of a Git commit, merge, or release.
- **UI-2 — Navigation and layout:** Planned incremental grouping and responsive navigation while retaining existing paths. The exact sidebar behavior and visual composition remain to be designed and approved.
- **UI-3 — Compliance Explorer UX:** Planned refinement of system/Profile selection, Requirements and Measures presentation, and contextual drill-down. The current Overview link to system measures opens the general Explorer at Requirements; a direct Measures deep link is a deferred UX issue, not an approved URL/state contract.
- Contextual links into editors may be developed in subsequent, separately scoped work. This ADR does not approve changes to mutation behavior or a new backend projection.
- For each frontend change, run applicable automated tests, lint, type checking, and production build. Complete manual workflow and browser acceptance testing after the relevant UX changes; existing automated guarantees are not deferred.
- Existing technical debt, including `TD-OLD-14` (navigation, accessibility, editor UX) and `TB-09f-04` (possible SystemWorkspace modularization), remains separately prioritized. This ADR does not mandate speculative refactoring.

## Alternatives considered

1. **Document/editor-first navigation as the primary UX:** Retain as available functional workflows, but reject as the overall information architecture because users must understand internal OSCAL artifacts before finding their tasks.
2. **Graph-first knowledge explorer:** Not selected as the primary interaction; relationships can be conveyed more accessibly and predictably through lists, detail views, and contextual navigation. A graph may be revisited as an optional aid.
3. **Separate role-specific applications or automatic role-based start pages:** Deferred. They would add complexity and risk conflating navigation preferences with authorization before there is a demonstrated need.
4. **Full frontend replacement or new UI framework:** Rejected for this phase because existing components, routes, data access, tests, and domain contracts can be reused incrementally.

## Consequences

### Benefits

- Users can begin with recognizable governance tasks while the underlying OSCAL-native domain remains intact.
- Shared data and distinct assessments are easier to discover without implying automatic equivalence or compliance.
- The workspace overview can change independently of domain workflows; phased delivery reduces migration and regression risk.

### Costs and limitations

- During transition, old and new navigation patterns may coexist; some workflows will still require additional clicks.
- Search, filtering, cross-perspective drill-down, and visual refinements must be limited to capabilities actually supported by existing endpoints and views unless separately approved.
- UI work requires explicit checks for accessibility, localization, direct-link compatibility, unsaved drafts, and concurrency conflict behavior.

## Open design questions

- Final responsive navigation layout, including sidebar expansion/collapse and active-state conventions.
- Placement and wording of cross-perspective links, especially for system-specific versus reusable measures.
- A safe, user-understandable deep-link/state model for opening the Explorer directly in Measures, if adopted.
- Whether role-based default views or relationship visualization would provide enough demonstrated value for later decisions.

## References

- `docs/adr/0003-tenant-aware-access.md`
- `docs/adr/0007-browser-bff-and-catalog-explorer.md`
- `docs/adr/0014-component-definition-library.md`
- `docs/adr/0018-frontend-internationalization.md`
- `docs/adr/0020-assessment-results.md`
- `docs/adr/0022-aggregate-optimistic-concurrency.md`
- `docs/adr/0024-compliance-explorer-read-model.md` (Proposed in the inspected snapshot)
- `TECHNICAL_DEBT.md`
- 