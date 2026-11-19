#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api_dir="$repo_root/apps/api"

npm_inventory="$repo_root/docs/npm-license-inventory.json"
py_runtime_inventory="$repo_root/docs/python-license-inventory.runtime.json"
py_dev_runtime_inventory="$repo_root/docs/python-license-inventory.dev-and-runtime.json"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

runtime_env="$tmpdir/runtime"
dev_env="$tmpdir/dev"

(
  cd "$api_dir"
  UV_PROJECT_ENVIRONMENT="$runtime_env" uv sync --locked --no-dev >/dev/null
  UV_PROJECT_ENVIRONMENT="$dev_env" uv sync --locked >/dev/null

  uv run --with pip-licenses pip-licenses \
    --python "$runtime_env/bin/python" \
    --format=json \
    --with-authors \
    --with-license-file \
    --output-file "$py_runtime_inventory" \
    >/dev/null

  uv run --with pip-licenses pip-licenses \
    --python "$dev_env/bin/python" \
    --format=json \
    --with-authors \
    --with-license-file \
    --output-file "$py_dev_runtime_inventory" \
    >/dev/null
)

(
  cd "$repo_root"
  npx license-checker --json --out "$npm_inventory"
)

python "$repo_root/scripts/normalize_license_inventory_paths.py"

python - "$npm_inventory" "$py_runtime_inventory" "$py_dev_runtime_inventory" <<'PY'
import json
import pathlib
import sys

npm_path = pathlib.Path(sys.argv[1])
runtime_path = pathlib.Path(sys.argv[2])
dev_runtime_path = pathlib.Path(sys.argv[3])

npm_data = json.loads(npm_path.read_text(encoding="utf-8"))
runtime_data = json.loads(runtime_path.read_text(encoding="utf-8"))
dev_runtime_data = json.loads(dev_runtime_path.read_text(encoding="utf-8"))

runtime_names = {entry.get("Name", "").lower() for entry in runtime_data}
dev_runtime_names = {entry.get("Name", "").lower() for entry in dev_runtime_data}

print(f"{npm_path}: packages={len(npm_data)}")
print(f"{runtime_path}: packages={len(runtime_data)}")
print(f"{dev_runtime_path}: packages={len(dev_runtime_data)}")
print(f"runtime_has_pytest={'pytest' in runtime_names} runtime_has_ruff={'ruff' in runtime_names}")
print(
    f"dev_runtime_has_pytest={'pytest' in dev_runtime_names} "
    f"dev_runtime_has_ruff={'ruff' in dev_runtime_names}"
)
PY
