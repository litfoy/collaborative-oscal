# AI usage in this project

Collaborative OSCAL uses human-led, AI-assisted development, including substantial use of agentic software engineering.

## Principles

- The human founder and maintainer leads product and architecture decisions and retains responsibility for project-level reviews, acceptance decisions, and releases.
- AI tools assist with implementation, specification, analysis, and technical review. Project-level reviews are conducted by the human founder and maintainer alongside AI-assisted reviews.
- AI-generated code or text is treated as untrusted until appropriately reviewed.
- Architecture and security requirements in ADRs and repository instructions take precedence over generated suggestions.
- Automated testing and documented architectural decisions support, but do not replace, human acceptance decisions.
- Contributors must not submit content they are not permitted to use.
- Substantial AI assistance should be disclosed in pull requests where it helps reviewers understand the change and verification performed.
- This project does not claim that all AI-assisted output has been manually reviewed or independently audited.

## Contributor responsibilities

When using AI assistance, contributors must:
- review generated output for correctness, security, and licensing impact
- run relevant tests/lint/type checks before proposing changes
- verify third-party code/data provenance before importing it
- keep attribution and license notices intact
- avoid sharing secrets or regulated data with external AI services

## Verification expectations

AI-assisted changes require the same or stricter checks as manual changes:
- focused tests for changed behavior
- lint and type checks for touched components
- explicit reporting of verification commands and outcomes

## Third-party IP and licensing

AI assistance does not change third-party licensing obligations.
Contributors must preserve notices, avoid unauthorized copying, and document
provenance for imported assets.
