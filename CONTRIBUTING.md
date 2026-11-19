# Contributing to Collaborative OSCAL

Thanks for contributing.

## Project scope and architecture

Before proposing a change, read:
- `README.md`
- `docs/development.md`
- `docs/architecture/overview.md`
- `docs/adr/`
- `.github/copilot-instructions.md`

Collaborative OSCAL is an alpha-stage modular monolith. Keep changes focused to
approved scope and preserve tenant isolation and OSCAL document integrity.

## Licensing and attribution

By contributing, you agree that your contribution is submitted under the
applicable project license:
- Apache-2.0 for project software
- CC-BY-4.0 for project-authored documentation

Project-authored documentation licensing details:
- `LICENSES/CC-BY-4.0.txt`
- scope definition in `README.md`

Project source files should include:
- `SPDX-License-Identifier: Apache-2.0`
- `Copyright The Collaborative OSCAL Authors.`

Do not remove or rewrite third-party notices. For third-party obligations see:
- `NOTICE`
- `THIRD_PARTY_NOTICES.md`
- `docs/license-compliance-assessment.md`

## Developer Certificate of Origin (DCO)

This project uses DCO sign-off instead of a CLA.

- Add sign-off to each commit:
  - `git commit -s`
- Equivalent manual trailer:
  - `Signed-off-by: Your Name <your.email@example.com>`

DCO sign-off certifies compliance with https://developercertificate.org/.

Manual GitHub enforcement configuration (repository settings):
- install and enable a DCO/sign-off status check app (or equivalent CI check)
- protect the default branch and require pull requests before merge
- require the DCO/sign-off status check to pass before merge
- disable direct pushes to the protected branch except for maintainers as needed

## Development setup

Use the existing setup instructions in `docs/development.md`.
Do not duplicate environment setup here.

## Required checks before pull request

Run relevant checks for the area you changed.

Backend:
```sh
cd apps/api
uv run ruff check .
uv run pytest
```

Frontend:
```sh
npm --workspace apps/web run lint
npm --workspace apps/web run typecheck
npm --workspace apps/web run test
```

If you changed dependency/license artifacts, also update inventories and notices
as documented in `docs/dependency-upgrade-progress.md` and
`docs/license-compliance-assessment.md`.

## Pull request expectations

- Keep PRs small and reviewable.
- Explain motivation, scope, and risk.
- Add/adjust tests for behavior changes.
- Document architectural decisions in `docs/adr/` when needed.
- Include verification commands and outcomes in the PR description.
- Confirm DCO sign-off is present on every commit.

## Security and conduct

- Security reports: see `SECURITY.md`.
- Community behavior expectations: see `CODE_OF_CONDUCT.md`.



