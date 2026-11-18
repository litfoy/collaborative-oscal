# Collaborative OSCAL

**Shared compliance data. Independent assessments.**

[Deutsch](README.de.md) · [Architecture](docs/architecture/overview.md) · [AI Governance demo](docs/architecture/ai-governance-demo-seed.md)

Collaborative OSCAL is an open-source, self-hosted proof of concept for collaborative governance, risk and compliance (GRC), built on [NIST OSCAL (Open Security Controls Assessment Language)](https://pages.nist.gov/OSCAL/).

It explores how information security, data protection, AI governance, risk management, compliance, system owners and auditors can work with shared information while retaining their distinct requirements, responsibilities and assessment judgments.

The central idea is to **document implementation once where appropriate, reuse information across frameworks, and assess it independently in each relevant context**. OSCAL provides the common machine-readable data foundation rather than merely an export format.

![Collaborative OSCAL](./assets/Collaborative%20OSCAL%20Governance%20Architecture.png)

*Conceptual overview: shared measures and system information, separate assessments. Independent findings are supported at the data-model level; a shared evidence library and fine-grained stakeholder authorization remain future work.*

> **Status: Experimental proof of concept.** Not intended for production use, confidential data or authoritative compliance decisions. The implementation demonstrates the approach but does not yet enforce full separation of stakeholder duties.

## Why Collaborative OSCAL?

Organizations often face overlapping requirements from several standards, regulations and internal policies. Different stakeholders may examine the same system, technical configuration or organizational measure, yet pursue different objectives and reach different conclusions.

Collaborative OSCAL separates three concerns:

- **Requirements:** Each normative or organizational catalog retains its identity, content and revision history. Explicit mappings describe relationships without equating compliance outcomes.
- **Implementation:** Reusable measures, concrete system components and requirement-specific implementation contributions are distinct. An implementation can contribute to several requirements without automatically satisfying them.
- **Assessment:** Assessment plans, observations and findings retain their own scope and historical context. A documented implementation is not evidence of its effectiveness; one finding does not automatically determine another assessment's outcome.

The longer-term vision is a shared information foundation with explicit reuse of suitable evidence, clear responsibilities and independent assessment authority. This is relevant to organizations with multiple governance and assurance functions, including regulated industries.

Potential frameworks include BSI IT-Grundschutz++, GDPR, ISO/IEC 27001 and 27002, NIST SP 800-53, NIST AI RMF, ISO/IEC 42001, the EU AI Act and internal policies, provided suitable OSCAL content and usage rights are available. These are intended use cases, not a claim of complete framework coverage or regulatory conformity.

### Example: multi-factor authentication

An information security officer assesses privileged access. A data protection officer considers the security of personal data processing under Article 32 GDPR. Both can refer to the same MFA measure and identity provider, but document separate contributions to their respective requirements and conduct separate assessments.

In the future, both could explicitly reuse the same suitable, versioned configuration export or test record while reaching different findings. MFA alone does not establish compliance with Article 32 GDPR.

## Quick start

With Docker and Docker Compose installed, run from the repository root:

```bash
docker compose up --build -d credentials db db-init api web
```

Or start the stack with the optional AI Governance demo dataset:

```bash
docker compose --profile ai-governance-demo up --build -d
```

Open [http://localhost:3000](http://localhost:3000). The standard demo includes a NIST SP 800-53 catalog. No external identity provider is required for local demo mode.

**Local demo only:** anyone who can access the demo frontend acts as the same demo user. Do not expose it publicly or use production or confidential data. The UI is available in English and German; the language setting does not translate imported OSCAL content or user-authored text.

See the [development guide](docs/development.md) for setup, configuration and testing. See the [AI Governance demo guide](docs/architecture/ai-governance-demo-seed.md) for seed status, troubleshooting and existing-installation behavior.

## AI Governance demo

The optional demo illustrates a fictional internal AI-assisted software development platform using selected controls from an OSCAL catalog based on the [NIST AI RMF Generative AI Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence).

It connects model and dataset versioning, human oversight, acceptable use policies, risk measurement and AI red teaming to reusable safeguards, concrete components and requirement-specific implementation contributions. It includes a versioned System Security Plan (SSP), Assessment Plan (AP) and Assessment Results (AR).

One example finding concerns traceability of model versions: two of three sampled fictional release records meet a local assessment objective and one does not. The finding applies to that objective only; it does not establish the status of the entire control or the other planned controls.

This is a documentation and assessment scenario, not a running AI agent platform. All scenario data and evidence links are fictional. It does not demonstrate actual compliance, certification or automated AI safety evaluation.

See the [scenario and seed documentation](docs/architecture/ai-governance-demo-seed.md) and [catalog provenance](examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json).

## Current capabilities

All implemented features are experimental.

| Area | Capabilities | Status |
| --- | --- | --- |
| Catalogs | Import, hierarchical browsing, immutable source revisions | Implemented |
| Profiles | Explicit control selection across catalog revisions | Implemented; full resolution deferred |
| Control mappings | Explicit cross-catalog relationships; no automatic compliance inference | Implemented |
| Component definitions | Reusable measures and controls | Implemented |
| Implementation register | Requirement-specific contributions and responsibilities | Implemented |
| Systems | Concrete system components | Implemented |
| System Security Plans (SSPs) | Catalog-based SSPs, validation, immutable document versions | Implemented |
| Assessment plans (APs) | Scope, objectives, subjects, activities, tasks, roles, pinned SSP versions | Implemented |
| Assessment results (ARs) | Reviewed controls, observations, evidence references, findings, pinned AP versions | Implemented |
| Independent assessments | Separate plans, results and findings in their respective contexts | Implemented at data-model level; fine-grained authorization pending |
| Shared assessment evidence | Versioned evidence library and reuse across assessments | Planned |
| Risks and POA&M | Risk treatment, remediation and tracking | Planned |

Additional capabilities include OIDC authentication, tenant-scoped authorization, English and German UI, and OSCAL JSON import and/or export as supported by each document model. Assessment Results evidence currently consists of references, not managed evidence file storage.

## Architecture

The application is a modular monolith with a Next.js / TypeScript web frontend, FastAPI / Python backend and PostgreSQL persistence. It uses [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle), OpenID Connect and Docker Compose.

Key design decisions:

- Imported catalog revisions and published SSP, AP and AR document versions are immutable. Historical references remain pinned to the original document state.
- Reusable measures, concrete components and requirement-specific implementation contributions remain separate. Control mappings do not transfer implementation or assessment status automatically.
- PostgreSQL combines authoritative OSCAL JSONB snapshots with relational identities, tenant boundaries and explicit references. Working records support editing before document version creation.
- OSCAL processing follows a Trestle-first approach, supplemented by official version-specific NIST JSON Schemas and application-level reference and integrity checks. This is not exhaustive OSCAL semantic validation.
- New documents use OSCAL 1.2.1 where supported by the authoring policy; imported and historical documents retain their declared versions and are not silently converted.

See the [architecture overview](docs/architecture/overview.md), [domain model](docs/architecture/domain-model.md) and [Architecture Decision Records](docs/adr/), including [SSPs](docs/adr/0017-system-security-plans.md), [Assessment Plans](docs/adr/0019-assessment-plans.md) and [Assessment Results](docs/adr/0020-assessment-results.md).

### OSCAL Compass and Compliance Trestle

[OSCAL Compass](https://oscal-compass.dev/) is an open-source project hosted by the Cloud Native Computing Foundation (CNCF). Its tools support OSCAL-based compliance authoring, validation and automation. In particular, [Compliance Trestle](https://github.com/oscal-compass/compliance-trestle) provides a CLI and SDK for working with OSCAL artifacts, while [Agile Authoring](https://github.com/oscal-compass/compliance-trestle-agile-authoring) supports GitOps-based collaborative authoring.

One of the original design goals of Collaborative OSCAL was to build on the OSCAL Compass ecosystem and reuse its tooling wherever practical, rather than reinvent OSCAL processing. Trestle's generated models and validation capabilities are integrated behind a dedicated adapter boundary ([ADR 0002](docs/adr/0002-oscal-adapter-boundary.md)). Official schemas and application checks complement them where needed.

Collaborative OSCAL explores a complementary approach: a browser-based, database-backed service for stakeholders who may not work with Git. The operational source of truth for compliance documents is the application database, not a Git repository; a GitOps workflow is deliberately not required for everyday use. This is a design choice for this use case, not a rejection of GitOps or compliance-as-code. Git-based workflows and further integration with OSCAL Compass tools may be valuable in the future. [Compliance to Policy (C2P)](https://github.com/oscal-compass/compliance-to-policy) is not yet integrated.

## Known limitations and roadmap

The POC demonstrates a catalog-to-assessment workflow, not a complete compliance management lifecycle. In particular:

- Semantic validation needs improvement: recursive recognition of normative assessment objectives and statements, local assessment method representation, stable assessment-step identities and reviewed objective scope are areas for correction or extension.
- Fine-grained stakeholder authorization, separation of duties, formal approvals and robust concurrent editing are not yet implemented. Existing tenant-level access controls must not be mistaken for independent assessment authority.
- Shared, versioned evidence management, structured evidence provenance and risk/POA&M workflows remain future work.
- Full profile resolution was intentionally deferred following compatibility testing. SSPs currently reference a catalog revision directly. Parameter authoring and resolution need further work.
- Structured custom catalog authoring, portable document bundles, human-readable reporting and broader interoperability testing are planned or require further development.

Schema-valid OSCAL documents do not establish regulatory compliance or guarantee interoperability with every OSCAL tool. See the [catalog import guide](docs/catalog-import.md), [profile resolution decision](docs/adr/0016-defer-profile-resolution.md) and [AI Governance interoperability findings](docs/architecture/ai-governance-demo-interoperability-findings-2026-11-17.md).

## Development and verification

Very large parts of the software were created through agentic coding, primarily with GitHub Copilot, using iterative prompt refinement and increasingly precise task specifications. ChatGPT supported design, specification and critical review. Human decisions, review and approval, documented architecture decisions and reproducible tests remain essential parts of the development process. AI-generated explanations and code are not treated as verified merely because they appear plausible.

The repository includes backend and frontend tests, PostgreSQL integration coverage, CI configuration, and compatibility and regression probes. The [Assessment Results compatibility notes](docs/architecture/assessment-results-compatibility-probes-2026-11-17.md) document additional checks performed during development. Test results from earlier development snapshots are not a release certification; run the current test suites and manual workflows as described in the [development guide](docs/development.md).

## Acknowledgements

- Collaborative OSCAL builds on the work of several open-source projects and communities:
- NIST OSCAL – the open standard underlying this project.
- OSCAL Compass – an ecosystem of tools and resources for OSCAL-based compliance.
- Compliance Trestle – OSCAL document processing and validation.
- OSCAL Compass Content – reusable OSCAL content, including the NIST AI RMF Generative AI catalog used in our demonstration.
- Thanks to the maintainers and contributors of these projects and the many open-source libraries that make Collaborative OSCAL possible.
- The project also benefits from the exchange of ideas within the LF AI & Data Security & Compliance Working Group.
- Collaborative OSCAL is an independent project and is not officially affiliated with or endorsed by NIST, OSCAL Compass or the Linux Foundation.

## License

The project's own software is licensed under [Apache License 2.0](LICENSE). Third-party catalogs and other external content remain subject to their respective licenses and attribution requirements; the software license does not relicense those materials.

## Further reading

- [NIST OSCAL](https://pages.nist.gov/OSCAL/)
- [OSCAL Compass](https://oscal-compass.dev/) · [GitHub](https://github.com/oscal-compass)
- [Compliance Trestle documentation](https://oscal-compass.github.io/compliance-trestle/)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [LF AI & Data](https://lfaidata.foundation/)
- [BSI – Stand-der-Technik-Bibliothek](https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek)
