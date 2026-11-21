#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${1:-$repo_root/artifacts/sbom}"

mkdir -p "$output_dir"

api_runtime="$output_dir/api-runtime.cyclonedx.json"
api_dev_runtime="$output_dir/api-dev-and-runtime.cyclonedx.json"
web_runtime="$output_dir/web-runtime.cyclonedx.json"
web_dev_runtime="$output_dir/web-dev-and-runtime.cyclonedx.json"

(
  cd "$repo_root/apps/api"
  uv export \
    --locked \
    --format cyclonedx1.5 \
    --no-dev \
    --preview-features sbom-export \
    --output-file "$api_runtime" \
    >/dev/null
  uv export \
    --locked \
    --format cyclonedx1.5 \
    --preview-features sbom-export \
    --output-file "$api_dev_runtime" \
    >/dev/null
)

(
  cd "$repo_root"
  npm sbom --sbom-format cyclonedx --package-lock-only --omit dev -w apps/web >"$web_runtime"
  npm sbom --sbom-format cyclonedx --package-lock-only -w apps/web >"$web_dev_runtime"
)

python - "$api_runtime" "$api_dev_runtime" "$web_runtime" "$web_dev_runtime" <<'PY'
import json
import pathlib
import sys

expected_spec_version = "1.5"
errors = []
validated = []

for raw_path in sys.argv[1:]:
    path = pathlib.Path(raw_path)

    if not path.exists():
        errors.append(f"{path}: missing SBOM file")
        continue
    if path.stat().st_size == 0:
        errors.append(f"{path}: SBOM file is empty")
        continue

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path}: invalid JSON ({exc})")
        continue

    if not isinstance(data, dict):
        errors.append(f"{path}: root JSON value must be an object")
        continue

    # Merge repeated npm dependency entries for unique CycloneDX items.
    dependencies = []
    by_ref = {}
    for dependency in data.get("dependencies", []):
        ref = dependency.get("ref")
        if ref in by_ref:
            existing = by_ref[ref]
            existing["dependsOn"] = list(dict.fromkeys(existing.get("dependsOn", []) + dependency.get("dependsOn", [])))
        else:
            normalized = dict(dependency)
            normalized["dependsOn"] = list(dict.fromkeys(normalized.get("dependsOn", [])))
            by_ref[ref] = normalized
            dependencies.append(normalized)
    if dependencies:
        data["dependencies"] = dependencies
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    bom = data.get("bomFormat")
    spec = data.get("specVersion")
    components = data.get("components")

    if bom != "CycloneDX":
        errors.append(f"{path}: bomFormat={bom!r}, expected 'CycloneDX'")
    if spec != expected_spec_version:
        errors.append(
            f"{path}: specVersion={spec!r}, expected {expected_spec_version!r}"
        )
    if not isinstance(components, list):
        errors.append(f"{path}: components must be an array")
        continue
    if not components:
        errors.append(f"{path}: components array must contain at least one entry")
        continue

    validated.append((path, len(components), spec))

if errors:
    print("SBOM validation failed:", file=sys.stderr)
    for message in errors:
        print(f"- {message}", file=sys.stderr)
    print(
        "Structural checks only: no independent CycloneDX schema validator is configured.",
        file=sys.stderr,
    )
    raise SystemExit(1)

for path, component_count, spec in validated:
    print(
        f"Validated {path.name}: bomFormat=CycloneDX specVersion={spec} "
        f"components={component_count}"
    )

print("Structural checks only: no independent CycloneDX schema validator is configured.")
PY
