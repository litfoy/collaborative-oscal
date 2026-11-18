# Dependency upgrade progress

_Last updated: 2026-11-18_

## Hardening Task 04 acceptance verification

- Rebuilt final web runtime image with current `infrastructure/docker/web.Dockerfile`.
- Recursively inspected runtime `node_modules` paths in `hardening04-web` image.
- Ran complete backend lint/test verification against disposable PostgreSQL database `collaborative_oscal_test`.
- Re-ran frontend lint/typecheck/tests/build against current lockfile state.
- Regenerated npm and Python license inventories and captured final audit outputs.
- Re-checked Dependabot PR state and latest `main` workflow run status.

## Runtime container findings

- Direct recursive directory scan findings:
  - No `minimatch` package directory was found.
  - No standalone `picomatch` package directory was found.
  - `next` contains bundled copy path: `/opt/app/apps/web/node_modules/next/dist/compiled/picomatch`.
  - `/opt/app/node_modules` includes multiple scope directories (`@typescript-eslint`, `@vitest`, `@eslint`) but scan did not find matching package manifests for targeted dev tools.
- Recursive `package.json` grep for target package names (`minimatch`, `picomatch`, `eslint`, `vitest`, `typescript`, `@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`) returned no hits in runtime manifests.
- Runtime limitation note:
  - Bundled/compiled vendor code shipped inside other packages (for example under `next/dist/compiled`) is not always represented as independently versioned install records. `npm audit` and package-manifest greps do not provide full provenance for those bundled assets.

## Key remediation details

- Initial runtime install with `npm ci --omit=dev --omit=optional` caused startup instability under non-root user:
  - `Unhandled Rejection: Error: EACCES: permission denied, mkdir '/opt/app/apps/web/node_modules/next/next-swc-fallback'`
- Corrective change: keep optional runtime dependencies (`npm ci --omit=dev`) so prebuilt SWC binaries are available and no write-at-runtime fallback is required.

## Verification results

- Backend lint:
  - `cd apps/api && uv run ruff check .`
  - Result: passed.
- Backend test suite (complete, locked environment):
  - `TEST_DATABASE_URL='postgresql+psycopg://postgres:postgres@127.0.0.1:54329/collaborative_oscal_test' uv run pytest`
  - Result: `341 passed`.
- Frontend checks:
  - `npm -w apps/web run lint`
  - `npm -w apps/web run typecheck`
  - `npm -w apps/web run test`
  - `npm -w apps/web run build`
  - Result: passed (`18` files, `167` tests).

## Security and license baseline

- Python vulnerabilities: none reported by `uv run --with pip-audit pip-audit`.
- Note from pip-audit: `collaborative-oscal-oscal` is local/non-PyPI and is skipped for public advisory matching.
- npm production vulnerabilities (`npm audit --omit=dev --json`): `0`.
- npm full audit (`npm audit --json`): `16` high findings, `1` remaining unique advisory chain (`picomatch`).
- License artifacts regenerated for current state:
  - `docs/npm-license-inventory.json`
  - `docs/python-license-inventory.dev-and-runtime.json`
  - `docs/python-license-inventory.runtime.json`
- LGPL/GPL review flags requiring maintainer/legal review before broad redistribution claims:
  - npm: `@img/sharp-libvips-darwin-arm64`, `@img/sharp-wasm32`
  - Python runtime: `paramiko`, `psycopg`, `psycopg-binary`

## Picomatch temporary risk-deferral proposal (draft)

- Remaining issue:
  - Advisory chain: `picomatch` (high), currently surfacing as dev-tooling findings.
- Project-specific exposure:
  - No standalone runtime package manifest hit for `picomatch` in production dependency graph.
  - Bundled `next/dist/compiled/picomatch` exists in runtime filesystem.
  - Public repository CI receives untrusted pull requests; parser/glob tooling can still be exercised during test/build phases.
- Mitigations in place:
  - Production container audit (`--omit=dev`) is clean.
  - Runtime image runs as non-root user.
  - Disposable CI/test infrastructure and isolated DB workflows are used.
- Additional mitigations proposed until remediation:
  - Keep CI execution limits strict (timeouts and resource limits on web test/build jobs).
  - Avoid running privileged credentials in workflows triggered from untrusted forks.
  - Continue pinning lockfiles and avoid implicit dependency drift.
- Proposed risk owner:
  - Maintainer/Release owner for `collaborative-oscal` (to assign named owner in milestone handoff).
- Proposed review date:
  - 2026-12-18 (or sooner if trigger condition occurs).
- Remediation triggers:
  - Compatible upstream release in Next/tooling chain that removes vulnerable `picomatch` path.
  - New exploit PoC demonstrating practical CI/runtime impact for this project layout.
  - Any change that increases untrusted input processing in build/test/runtime path.

## Dependabot and CI status

- Open Dependabot PRs (GitHub API): `0`.
- Latest `main` push CI run status:
  - `86d9a05`: success.
- Previously failing `main` run for `da5b896` still exists historically:
  - run `44265780895`: `web` job failure, `api-quick` success, `api-integration` skipped.

## Reproducible license inventory commands

- npm inventory (existing process):
  - `npx license-checker --json --out docs/npm-license-inventory.json`
- Python inventories:
  - `cd apps/api && uv run --with pip-licenses pip-licenses --format=json --with-authors --with-license-file --output-file /Users/rib/workspace/collaborative-oscal/docs/python-license-inventory.dev-and-runtime.json`
  - `cd apps/api && uv run --no-dev --with pip-licenses pip-licenses --format=json --with-authors --with-license-file --output-file /Users/rib/workspace/collaborative-oscal/docs/python-license-inventory.runtime.json`

## Hardening Task 05 pre-work obligations (unresolved)

- Confirm attribution and redistribution obligations for LGPL-bearing dependencies in npm/Python runtime stacks.
- Verify whether bundled third-party code under framework-compiled paths requires additional attribution treatment beyond package-level inventory.
- Define release artifact scope for license notices (source distribution vs container image vs demo deployment).
- Record legal/maintainer decision and tracking issue before public release claim.

## Known limitations and follow-ups

- `picomatch` chain remains unresolved with no compatible, non-disruptive patch path identified in current toolchain constraints.
- No risk acceptance is recorded here; maintainer decision is still required for deferred vulnerability and licensing obligations.













