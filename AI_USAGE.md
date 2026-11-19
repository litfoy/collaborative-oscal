# AI usage in this project

Collaborative OSCAL uses human-led, AI-assisted development.

## Principles

- Humans remain responsible for design, review, verification, and release.
- AI-generated code or text is treated as untrusted until reviewed.
- Architecture and security requirements in ADRs and repository instructions
  take precedence over generated suggestions.
- Contributors must not submit content they are not permitted to use.

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

## Transparency

Contributors are encouraged to disclose substantial AI assistance in pull
requests when it helps reviewers understand risk and verification performed.

