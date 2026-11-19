# Third-party notices

This repository contains project code and bundled third-party content.
Project code is licensed under Apache-2.0. Third-party assets and dependencies
retain their original licenses.

## Bundled non-code content

### NIST OSCAL JSON Schemas
- Location: `packages/oscal/src/collaborative_oscal_oscal/schemas/`
- Source: official `usnistgov/OSCAL` release assets
- Provenance and checksums: `docs/catalog-import.md`
- Version-pinned upstream license reference: `https://github.com/usnistgov/OSCAL/blob/v1.2.1/LICENSE.md`
- Applicable upstream statement (v1.2.1): public domain in the United States
  (17 U.S.C. 105), worldwide CC0 1.0 dedication, and NIST notice/attribution
  terms for redistribution and modifications
- Original notice text included at: `LICENSES/NIST-OSCAL-v1.2.1-LICENSE.md`
- Redistribution note: preserve provenance and schema integrity checks documented in `docs/catalog-import.md`

### NIST SP 800-53 Rev. 5 fixture
- Location: `apps/api/tests/fixtures/NIST_SP-800-53_rev5_catalog-min.json`
- Source: `usnistgov/oscal-content` release `v1.5.0`
- Provenance and checksum: `docs/catalog-import.md`
- Version-pinned upstream license reference: `https://github.com/usnistgov/oscal-content/blob/v1.5.0/LICENSE.md`
- Applicable upstream statement (v1.5.0): public domain in the United States,
  worldwide CC0 1.0 dedication, and NIST license notice terms
- Original notice text included at:
  `LICENSES/NIST-OSCAL-content-v1.5.0-LICENSE.md`
- Redistribution note: treat as third-party normative content

### NIST AI RMF Generative AI catalog
- Location: `examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.json`
- Provenance metadata: `examples/catalogs/nist-ai-rmf-gen-ai-1.0.0-catalog.provenance.json`
- Upstream: `oscal-compass/oscal-content`
- Declared license identifier in provenance: `Apache-2.0`

### BSI Grundschutz++ content
- Locations:
  - `examples/catalogs/Grundschutz++-resolved_catalog.json`
  - `apps/api/tests/fixtures/Grundschutz++-resolved_catalog.json`
- Upstream repository: `BSI-Bund/Stand-der-Technik-Bibliothek`
- Pinned upstream commit: `c3f37859`
- Pinned upstream file:
  - `control_layer/Grundschutz++/Grundschutz++-resolved_catalog.json`
  - blob URL: `https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek/blob/c3f37859/control_layer/Grundschutz%2B%2B/Grundschutz%2B%2B-resolved_catalog.json`
- Verified SHA-256 for upstream and both bundled copies:
  - `592410c513691c18631402db3982dda6a4530dd6f2960868a6999017d311fa28`
- License at the same commit: `CC-BY-SA-4.0`
  - license URL: `https://github.com/BSI-Bund/Stand-der-Technik-Bibliothek/blob/c3f37859/LICENSE`
- Attribution: Bundesamt fuer Sicherheit in der Informationstechnik (BSI)
- Redistribution status: redistributed unmodified from the pinned upstream file
- Provenance manifest: `examples/catalogs/Grundschutz++-resolved_catalog.provenance.json`

## Dependency license inventories

The dependency license inventories are generated from lockfiles and normalized to
workspace-relative paths:
- `docs/npm-license-inventory.json`
- `docs/python-license-inventory.runtime.json`
- `docs/python-license-inventory.dev-and-runtime.json`

Generation/normalization scripts:
- `scripts/normalize_license_inventory_paths.py`
- commands in `docs/dependency-upgrade-progress.md`

## Copyleft and exception licenses requiring review

The following dependency licenses were detected and need explicit maintainer/legal
review before making broad redistribution claims:
- LGPL: `paramiko`, `psycopg`, `psycopg-binary`, `@img/sharp-libvips-darwin-arm64`
- MPL-2.0: `certifi`, `orjson`, `axe-core`
- CC-BY-4.0: `caniuse-lite`
- BlueOak-1.0.0: `@isaacs/nonrecursive-glob-match`

These findings are documented in detail with release-risk classification in
`docs/license-compliance-assessment.md`.

## License-text sources

- Apache-2.0 text: `LICENSE`
- CC-BY-4.0 text: `LICENSES/CC-BY-4.0.txt`
- CC-BY-SA-4.0 text: `LICENSES/CC-BY-SA-4.0.txt`
- NIST OSCAL v1.2.1 license notice: `LICENSES/NIST-OSCAL-v1.2.1-LICENSE.md`
- NIST OSCAL content v1.5.0 license notice:
  `LICENSES/NIST-OSCAL-content-v1.5.0-LICENSE.md`
- Python dependency full license texts: embedded in
  `docs/python-license-inventory.runtime.json` and
  `docs/python-license-inventory.dev-and-runtime.json` (`LicenseText` fields)
- npm dependency license file paths are listed in `docs/npm-license-inventory.json`
  (paths are workspace-relative; package files are not committed in this repository)




