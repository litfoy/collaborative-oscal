# License compliance assessment

_Last updated: 2026-11-19_

This assessment documents current license posture for source-code distribution
and locally built Docker images used by contributors. It is not legal advice
and does not claim final legal compliance.

## Authoritative references used

- Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0
- CNCF copyright notices: https://github.com/cncf/foundation/blob/main/copyright-notices.md
- CNCF license notices: https://github.com/cncf/foundation/blob/main/license-notices.md
- CNCF allowlist policy: https://github.com/cncf/foundation/blob/main/policies-guidance/allowed-third-party-license-policy.md
- Linux Foundation generative AI guidance: https://www.linuxfoundation.org/legal/generative-ai
- DCO: https://developercertificate.org/
- Contributor Covenant: https://www.contributor-covenant.org/

## Repository licensing state

- Root `LICENSE` remains unmodified Apache-2.0.
- Root `NOTICE` added with project and upstream attribution context.
- Project-owned source files now include:
  - `SPDX-License-Identifier: Apache-2.0`
  - `Copyright The Collaborative OSCAL Authors.`
- Project-authored documentation is licensed under CC-BY-4.0 with license text
  at `LICENSES/CC-BY-4.0.txt` and scope defined in `README.md`.
- Third-party content and lockfiles were not relicensed or rewritten.

## Bundled third-party content review

### OSCAL schemas
- Bundled official NIST JSON Schemas are in
  `packages/oscal/src/collaborative_oscal_oscal/schemas/`.
- Provenance and per-version hashes are documented in `docs/catalog-import.md`.
- Action: keep as third-party assets with provenance preserved.

### Normative/example catalog content
- NIST SP 800-53 fixture:
  `apps/api/tests/fixtures/NIST_SP-800-53_rev5_catalog-min.json`
- NIST AI RMF GenAI catalog:
  `examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.json`
  with provenance file
  `examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json`.
- BSI Grundschutz++ catalog copies:
  - `examples/catalogs/Grundschutz++-resolved_catalog.json`
  - `apps/api/tests/fixtures/Grundschutz++-resolved_catalog.json`
- Verified upstream provenance for BSI catalog:
  - upstream repo: `https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek`
  - pinned commit: `c3f37859`
  - pinned path: `control_layer/Grundschutz++/Grundschutz++-resolved_catalog.json`
  - SHA-256 (upstream and both bundled copies):
    `592410c513691c18631402db3982dda6a4530dd6f2960868a6999017d311fa28`
  - license at same commit: `CC-BY-SA-4.0`
  - provenance manifest:
    `examples/catalogs/Grundschutz++-resolved_catalog.provenance.json`
  - redistribution state: unmodified copy

## Dependency inventory and reproducibility

Inventories retained and normalized to workspace-relative paths:
- `docs/npm-license-inventory.json`
- `docs/python-license-inventory.runtime.json`
- `docs/python-license-inventory.dev-and-runtime.json`

Local generation:
- `chmod +x scripts/generate_license_inventories.sh`
- `scripts/generate_license_inventories.sh`

CycloneDX SBOM generation (application dependencies only):
- `chmod +x scripts/generate_sboms.sh`
- `scripts/generate_sboms.sh`
- outputs under `artifacts/sbom/` (not committed)

CI artifact availability:
- `.github/workflows/ci.yml` includes `sbom` job on `push` and `pull_request`
- uploads `artifacts/sbom/` as `sbom-${GITHUB_SHA}`

## License classification summary

### Generally Apache-2.0-compatible permissive licenses
Examples observed in lockfile-derived inventories:
- MIT / BSD variants / ISC / Apache-2.0 / PSF-2.0 / 0BSD / MIT-0 / Unlicense

### Additional obligations or policy exceptions
These require explicit maintainer/legal review for release positioning:
- LGPL-2.1 (`paramiko`)
- LGPL-3.0-only (`psycopg`, `psycopg-binary`)
- LGPL-3.0-or-later (`@img/sharp-libvips-darwin-arm64`)
- MPL-2.0 (`certifi`, `orjson`, `axe-core`)
- CC-BY-4.0 (`caniuse-lite`)
- BlueOak-1.0.0 (`@isaacs/nonrecursive-glob-match`) and other non-core
  permissive licenses should be reviewed against the CNCF allowlist policy as a
  technical benchmark.

### Unknown/unclear licensing signals to track
- none currently identified for project-owned npm workspace packages after explicit
  `Apache-2.0` metadata was added.

## SBOM scope limitations

- The generated CycloneDX files model lockfile-resolved application dependencies
  for `apps/api` and `apps/web` only.
- These SBOMs are not complete OCI image SBOMs and do not enumerate base-image
  packages, OS packages, or runtime filesystem artifacts outside the application
  dependency graphs.

## Actual redistribution obligations (current distribution model)

For source-code distribution and locally built Docker images:
- preserve Apache-2.0 notices for project software
- preserve third-party notices and provenance records
- for bundled BSI Grundschutz++ catalog under CC-BY-SA-4.0, retain required
  attribution, include CC-BY-SA-4.0 license text, and indicate whether changes
  were made (current state: redistributed unmodified)

## Container distribution considerations

Compose/Docker references include third-party base images (e.g. Python, Node,
PostgreSQL, `ghcr.io/astral-sh/uv`).

For container redistribution readiness, maintainers must additionally verify:
- upstream image license terms and notice obligations,
- whether OCI image notice bundles are needed,
- binary-redistribution obligations for transitive native libraries.

## Actual obligations vs policy-reference exceptions

Actual legal/redistribution obligations for this project are determined by
applicable licenses of distributed artifacts (project code, project docs,
bundled third-party content, dependencies, and container bases).

The CNCF Allowlist License Policy is retained here as a neutral technical
reference for identifying license types that may require exception handling in
other governance contexts. It is not treated as a project objective, roadmap,
or affiliation requirement.

## CNCF allowlist policy assessment (technical reference)

This repository includes licenses commonly accepted for open-source projects,
but current lockfiles also include licenses that may require exception handling
under that policy reference.

No CNCF or Linux Foundation affiliation is claimed.

## CC-BY-4.0 documentation licensing scope (adopted)

Project-authored documentation is licensed under CC-BY-4.0.

Included scope:
- root docs: `README.md`, `README.de.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, `MAINTAINERS.md`, `AI_USAGE.md`
- project-authored Markdown under `docs/` unless a file clearly identifies
  third-party ownership or different license terms

Excluded scope:
- software source code and scripts (Apache-2.0)
- third-party or copied normative artifacts (including bundled catalogs,
  fixtures, schemas, and provenance manifests)
- machine-generated dependency inventories in `docs/`

## Release blockers vs backlog

### Release blockers
- Approve handling for LGPL/MPL/CC-BY dependencies in intended distribution model.
- Define container redistribution notice strategy if container images are distributed.

### Backlog items
- Automate periodic inventory regeneration in CI.
- Add explicit workflow checks for SPDX header presence in new source files.
- Add documented legal-review checklist for release candidates.
