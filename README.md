# Collaborative OSCAL

**Shared compliance data. Independent assessments.**

[Deutsch](README.de.md) · [Architecture](docs/architecture/overview.md) · [AI Governance demo](docs/architecture/ai-governance-demo-seed.md)

Collaborative OSCAL is an independent, self-hosted, open-source platform for collaborative governance, risk and compliance (GRC). The project is in **alpha development** and uses [NIST OSCAL (Open Security Controls Assessment Language)](https://pages.nist.gov/OSCAL/) as its native information model—not merely as an import/export format.

Its purpose is to reduce redundant work across data protection, information security, AI safety, AI governance and other governance domains, as well as providing an API for Compliance Automation. Information about systems, safeguards and implementation can be reused where appropriate, while requirements, responsibilities and assessment judgments remain distinct.

**Document an implementation once where appropriate; reuse relevant information across frameworks; assess each requirement independently in its own context.**

![Collaborative OSCAL](./assets/Collaborative%20OSCAL%20Governance%20Framework.png)

*Conceptual overview: shared safeguards and system information, separate assessments. Independent findings are supported in the data model; shared evidence management and fine-grained stakeholder authorization remain future work.*

> **Alpha status:** Collaborative OSCAL is not intended for production use, confidential data or authoritative compliance decisions. It has not undergone an independent security audit or completed the hardening and separation-of-duties work expected of production GRC software. No formal production readiness or regulatory conformity is claimed.

## Why Collaborative OSCAL?

Organizations must address requirements from multiple standards, regulations and internal policies. Different specialists may inspect the same system or safeguard but have different mandates, criteria and conclusions.

Collaborative OSCAL keeps three concerns separate:

- **Requirements:** Each source catalog and its revisions retain their identities. OSCAL Profiles select controls for a particular scope; selection alone does not establish legal applicability. Explicit cross-catalog mappings describe relationships without asserting equivalence.
- **Implementation:** Reusable component definitions, concrete system components and control-specific implementations are distinct. One safeguard may support several controls without automatically satisfying any of them.
- **Assessment:** Assessment Plans and Results retain their own scope, observations, findings and historical references. A documented implementation is not proof of effectiveness, and one assessment cannot automatically decide another's outcome.

The longer-term goal is a common information foundation with explicit reuse of suitable evidence, clear responsibilities and independent assessment authority.

Potential use cases include BSI IT-Grundschutz++, GDPR, ISO/IEC 27001 and 27002, NIST SP 800-53, NIST AI RMF, ISO/IEC 42001, the EU AI Act and internal policies—subject to suitable OSCAL content and permission to use it. This is **not** a claim of complete framework coverage or regulatory compliance.

### Example: multi-factor authentication

An information security officer assesses privileged access. A data protection officer examines the security of personal-data processing under Article 32 GDPR. Both may reference the same MFA safeguard and identity provider, but document separate contributions and reach independent assessment conclusions.

In a future shared evidence library, the two functions might explicitly reuse the same appropriate, versioned configuration export or test record. MFA by itself does not establish GDPR compliance.

## Quick start

With Docker Compose v2 or newer installed, run from the repository root:

```bash
docker compose up --build -d
```

Open [http://localhost:3000](http://localhost:3000). Local demo startup initializes the Acme workspace, imports the NIST SP 800-53 baseline catalog and applies the AI Governance / Governance Coverage seed before the API and web app start. The seed includes NIST GenAI and EU AI Act catalogs, demonstration mappings and fictional systems. No external identity provider is needed in local demo mode.

**Local demo only:** Anyone who can reach the demo frontend acts as the same demo user. Do not expose this mode publicly or use real, production or confidential data. The UI supports English and German; changing the language does not translate imported OSCAL material or user-authored content.

The Compliance Explorer can be opened from the application navigation. It requires an information system and **one to five existing Profiles** to explore. The default governance seed does not automatically create Explorer-ready Profiles; create or select Profiles first. Choosing a Profile for exploration does not establish that it is applicable to the selected system.

See the [development guide](docs/development.md) for setup and tests, and the [AI Governance demo guide](docs/architecture/ai-governance-demo-seed.md) for seed behavior and troubleshooting. Existing local demo data should not be reset without understanding the consequences.

## AI Governance demo

The included scenario depicts a **fictional** internal AI-assisted software development platform and selected controls from an OSCAL catalog based on the [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence).

It connects model and dataset versioning, human oversight, acceptable-use policies, risk measurement and AI red teaming to reusable safeguards, concrete components and control-specific implementation contributions. The scenario includes a versioned System Security Plan (SSP), Assessment Plan (AP) and Assessment Results (AR).

One example finding concerns model-version traceability: two of three fictional release records meet a local assessment objective and one does not. The finding addresses **that objective**, not automatically the complete control or any other requirement.

The Governance Coverage extension adds EU AI Act controls and explicit cross-catalog demonstration mappings. Mapping relationships are not validated claims of regulatory equivalence. The scenario is not a running AI agent platform, and its data and evidence links are fictional; it does not establish compliance, certification or real AI safety performance.

See the [scenario and seed documentation](docs/architecture/ai-governance-demo-seed.md) and [catalog provenance](examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json).

## Current capabilities

These are experimental alpha capabilities—not a guarantee that every OSCAL construct or workflow is supported.

| Area | Implemented capability or status |
| --- | --- |
| Catalogs | Import, hierarchical browsing and immutable source revisions. |
| Profiles | Explicit control selection from multiple pinned catalog revisions; full OSCAL Profile Resolution is deferred. |
| Control mappings | Explicit cross-catalog relationships, without automatic equivalence or compliance inference. |
| Component definitions | Reusable safeguards represented through OSCAL Component Definitions. |
| Systems and implementation register | Information systems, concrete system components and requirement-specific implementation records. |
| Compliance Explorer (C-light) | **Read-only** Requirements and Measures views for a selected system and one to five Profiles. Shared source controls are deduplicated with Profile memberships retained; only implementations explicitly linked to the selected system are displayed. |
| System Security Plans (SSPs) | Catalog-based plans, validation, explicit implementation membership and immutable published document versions. |
| Assessment Plans (APs) | Scope, objectives, subjects, activities, tasks, roles and references to historical SSP versions. |
| Assessment Results (ARs) | Human-authored or imported assessed controls, observations, evidence references and findings linked to historical AP versions. |
| Assessment automation | Authenticated, tenant-scoped REST import of supported native OSCAL 1.2.1 Assessment Results JSON into the existing working/publication lifecycle. |
| Publication and history | Mutable working records with immutable published SSP/AP/AR snapshots and pinned historical references. |
| Optimistic concurrency | Aggregate-level protection implemented and accepted for APs, ARs, SSPs, Profiles, Mapping Collections, Component Definitions, Information Systems, individual System Components and Control Implementations (including Responsibilities). |
| Supply-chain visibility | CycloneDX dependency SBOM generation for Python/API and npm/web runtime and development dependencies, configured in CI. |
| Shared evidence management | Managed, versioned evidence storage and reuse across assessments: **not implemented**. |
| Risk and POA&M management | Dedicated risk treatment and remediation workflows: **not implemented**. |

The Compliance Explorer's **Measures** grouping covers only the Controls on the currently loaded, server-paginated page; it is not yet a complete, globally paginated measures inventory. It does not display assessment conclusions or cross-catalog mappings, calculate a compliance score, infer applicability or establish a persistent System-to-Profile assignment. Controls with no system-linked implementation remain visible as **not documented for that system**, not automatically non-compliant.

Native OSCAL Assessment Results import uses the same working-state validation, pinned AP context and publication lifecycle as human-authored results. Evidence is currently represented by OSCAL references, not managed evidence files. See the [Assessment Results REST Import guide](docs/assessment-result-import.md).

Other capabilities include OIDC authentication, tenant-scoped authorization, English/German UI and native OSCAL JSON import/export for supported document models. Validation combines maintained OSCAL models, applicable official NIST schemas and application integrity checks; it does not cover every possible semantic condition.

## Architecture

Collaborative OSCAL is a **modular monolith**: Next.js / React / TypeScript frontend, Python / FastAPI backend, SQLAlchemy and PostgreSQL persistence, and browser BFF. It uses OpenID Connect and Docker Compose.

The main architectural principles are:

- **OSCAL first:** Preserve OSCAL concepts, identifiers and document semantics wherever possible. Application-specific persistence, authorization and working-state concerns are modeled separately.
- **Historical immutability:** Imported catalog revisions and published SSP/AP/AR snapshots are immutable. Later changes to shared data do not rewrite historical publications. Working records can continue evolving between publications.
- **Explicit references:** Profile selections, catalog revisions, mappings, system components and implementations have typed, verifiable relationships. A matching title is not a matching identity.
- **Independent assessments:** Sharing a safeguard, system component or implementation does not imply equivalent control requirements or identical findings.
- **Concurrency and tenant isolation:** Mutable aggregates use the established optimistic-concurrency contract where implemented, with tenant-aware authorization; frontend conflict handling must not silently discard unsaved user work.
- **Reuse before reinvention:** OSCAL processing uses Compliance Trestle behind an adapter boundary, official version-specific NIST JSON Schemas and application-specific integrity checks.

New documents generally use OSCAL 1.2.1 under the project's supported authoring policy. Imported and historical artifacts retain their declared versions rather than being silently converted.

See the [architecture overview](docs/architecture/overview.md), [domain model](docs/architecture/domain-model.md), [Architecture Decision Records](docs/adr/), [aggregate concurrency ADR](docs/adr/0022-aggregate-optimistic-concurrency.md), [SSP ADR](docs/adr/0017-system-security-plans.md), [AP ADR](docs/adr/0019-assessment-plans.md) and [AR ADR](docs/adr/0020-assessment-results.md).

### Why Python? OSCAL Compass and Compliance Trestle

Python was deliberately chosen for the backend to work with the existing OSCAL tooling ecosystem, especially [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle), rather than implement a separate OSCAL processing stack or optimize solely for the maintainer's previous programming-language experience.

[OSCAL Compass](https://oscal-compass.dev/) provides open-source tooling for OSCAL-based authoring, validation and automation. Trestle offers a Python CLI and SDK, while [Agile Authoring](https://github.com/oscal-compass/compliance-trestle-agile-authoring) supports GitOps-based collaborative authoring. Collaborative OSCAL builds on that ecosystem but is an **independent project**, not an OSCAL Compass subproject or an officially endorsed CNCF/LF initiative.

Trestle's models and validation capabilities are kept behind a dedicated [adapter boundary (ADR 0002)](docs/adr/0002-oscal-adapter-boundary.md), complemented by official OSCAL schemas and application-level reference checks.

Collaborative OSCAL explores a complementary, **browser-based and database-backed** workflow for stakeholders who do not work in Git every day. The application's operational source of truth is its database, not a Git repository. This does not reject GitOps or compliance-as-code; future integration with other OSCAL tools remains possible. [Compliance to Policy (C2P)](https://github.com/oscal-compass/compliance-to-policy) is not currently integrated.

## Known limitations and roadmap

The project is still an alpha: semantic validation is incomplete, fine-grained stakeholder authorization and separation of duties are not finished, several workflows are absent, and additional security and operational hardening is needed. Automated tests and architectural documentation do not establish production readiness.

The **aggregate-level optimistic-concurrency rollout has been implemented and accepted** for the aggregates listed above. Some older ADR/guide rollout-status passages have not yet been synchronized with the completed implementation reviews; the architectural contract itself remains applicable.

### Current and prospective work

The order and exact scope of these items are subject to maintainer decisions:

- Complete the manual Compliance Explorer acceptance walkthrough using the fictional demo data, then improve frontend information architecture and user experience.
- Expand the Explorer beyond page-local Measures grouping; consider a Control/Profile difference view and richer, explicitly sourced cross-domain relationships.
- Add shared Parties, Roles and Responsibilities management.
- Introduce native OSCAL Inventory Items, broader assessment subjects and a system/inventory overview.
- Support browser-based custom OSCAL Catalog authoring with explicit identity and revision semantics.
- Develop a more curated cross-domain governance demonstration and broaden catalog availability where content rights permit.
- Continue security, development verification, CI/release and operational hardening as risk and release needs require.

### Longer-term plans

- Shared, versioned assessment evidence and explicit cross-assessment reuse.
- Risk management and POA&M workflows.
- Improved OSCAL interoperability, portable document workflows and reporting.
- Finer-grained authorization, review responsibilities and formal approvals.
- Stronger semantic validation of objectives, methods, steps and reviewed scope.
- Further Profile Resolution and parameter authoring.

Schema-valid OSCAL documents do not by themselves establish regulatory compliance or guarantee interoperability with every OSCAL tool. See the [catalog import guide](docs/catalog-import.md), [Profile Resolution decision](docs/adr/0016-defer-profile-resolution.md) and [AI Governance interoperability findings](docs/architecture/ai-governance-demo-interoperability-findings-2026-11-17.md).

### Path to beta

A **substantial code consolidation, refactoring and maintainability review is planned before any beta release**. Its scope will be driven by documented technical debt, focused architecture and security findings, test evidence, manual acceptance results and contributor feedback. This is not a commitment to rewrite the backend or replace its OSCAL-native model. Independent review of security-critical and Python-specific implementation paths is particularly welcome.

## Development and verification

Development is **human-led and substantially AI-assisted**, including agentic coding tools. The founder and maintainer has a background in **backend development with Java and C**, software architecture and governance, but does **not** claim extensive hands-on Python experience. The choice of Python is intentional for ecosystem and reuse reasons, as described above; AI assistance is part of the implementation workflow, not the rationale for the language choice.

The maintainer retains responsibility for product direction, architecture, acceptance and releases. AI tools assist with specification, coding, analysis and reviews. Changes are evaluated through human-led review, focused automated tests and documented architectural decisions, but **not all generated code has been independently or manually audited**. Neither green tests nor AI review replace independent code and security reviews. Contributions from experienced Python developers and reviewers are particularly welcome.

The repository includes backend and frontend suites, PostgreSQL integration tests, CI configuration and reproducible development procedures. The [Assessment Results compatibility notes](docs/architecture/assessment-results-compatibility-probes-2026-11-17.md) document additional development checks. Historical test reports are not release certification; execute the current checks and manual workflows described in the [development guide](docs/development.md). Further AI-use expectations are in [AI_USAGE.md](AI_USAGE.md).

## Project governance and contribution

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution requirements, [MAINTAINERS.md](MAINTAINERS.md) for maintainer responsibilities and [SECURITY.md](SECURITY.md) for responsible vulnerability reporting. Project use of AI and contributor expectations are documented in [AI_USAGE.md](AI_USAGE.md).

## Acknowledgements

Collaborative OSCAL builds on the work of many open-source projects and communities:

- [NIST OSCAL](https://pages.nist.gov/OSCAL/) — the underlying open standard.
- [OSCAL Compass](https://github.com/oscal-compass) — tools and resources for OSCAL-based compliance workflows.
- [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle) — OSCAL document processing and validation.
- [OSCAL Compass Content](https://github.com/oscal-compass/oscal-content) — reusable content, including the NIST AI RMF Generative AI catalog used in the demo.
- The maintainers, contributors and other open-source libraries that make this project possible.
- Exchanges of ideas in the LF AI & Data Security & Compliance Working Group.

Collaborative OSCAL is independent and is **not officially affiliated with or endorsed by** NIST, OSCAL Compass, CNCF or the Linux Foundation.

## License

The project's own software is licensed under the [Apache License 2.0](LICENSE), with project attribution notices in [NOTICE](NOTICE).

Third-party catalogs, schemas, fixtures, dependencies and container contents retain their respective licenses and attribution obligations. The software license does **not** relicense third-party material. See:

- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- [docs/license-compliance-assessment.md](docs/license-compliance-assessment.md)
- [docs/npm-license-inventory.json](docs/npm-license-inventory.json)
- [docs/python-license-inventory.runtime.json](docs/python-license-inventory.runtime.json)

Project-authored documentation is licensed under [Creative Commons Attribution 4.0 International](LICENSES/CC-BY-4.0.txt) (CC-BY-4.0), including these root files: `README.md`, `README.de.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `MAINTAINERS.md`, `AI_USAGE.md`, and project-authored Markdown under `docs/` unless marked otherwise.

Excluded from that documentation license are software and scripts (Apache-2.0), third-party or copied normative content (which retains its own licenses), schemas, fixtures, provenance files and machine-generated dependency inventories in `docs/`.

## Further reading

- [NIST OSCAL](https://pages.nist.gov/OSCAL/)
- [OSCAL Compass](https://oscal-compass.dev/) · [GitHub](https://github.com/oscal-compass)
- [Compliance Trestle documentation](https://oscal-compass.github.io/compliance-trestle/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [LF AI & Data](https://lfaidata.foundation/)
- [BSI – Stand-der-Technik-Bibliothek](https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek)
