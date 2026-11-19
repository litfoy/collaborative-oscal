# Maintainers

## Current maintainer

- Founder and maintainer: GitHub account `@litfoy`

Repository: https://github.com/litfoy/collaborative-oscal

## Responsibilities

Maintainers are expected to:
- keep project scope aligned with architecture and ADRs
- review and merge changes that meet quality and security requirements
- maintain release, dependency, and license hygiene
- triage issues, security reports, and community reports
- enforce `CODE_OF_CONDUCT.md`

## Lightweight decision process

1. Propose changes in an issue or pull request.
2. Discuss trade-offs with references to docs/ADRs.
3. Maintainer records the decision in the PR and, when architectural,
   in `docs/adr/`.
4. Significant security/license risks require explicit maintainer sign-off.

## Escalation categories

The following require explicit maintainer approval before merge:
- dependency additions or license-risk changes
- changes affecting tenant isolation or trust boundaries
- schema/version policy changes for OSCAL authoring/import paths
- governance policy changes (`SECURITY.md`, `CODE_OF_CONDUCT.md`, DCO policy)

