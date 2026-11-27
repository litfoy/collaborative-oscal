#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: ./run_all_tests.sh [--dry-run]

Runs test suites for all applications in this repository:
- apps/api (pytest via uv)
- apps/web (vitest via npm workspace)

Behavior:
- If TEST_DATABASE_URL is set, API PostgreSQL integration tests are included.
- If TEST_DATABASE_URL is not set, integration tests are expected to be skipped.
- If TEST_DATABASE_OWNER_URL, TEST_DATABASE_RUNTIME_URL and TEST_DATABASE_PROVISIONER_URL
  are set, separate-role database tests run and are required (--require-database-roles).
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is required but not installed or not on PATH." >&2
    return 1
  fi
}

run_or_print() {
  local label="$1"
  local cmd="$2"

  echo "==> $label"
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "$cmd"
    return 0
  fi

  bash -lc "$cmd"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument '$1'" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_cmd uv
require_cmd npm

status=0
api_test_cmd="cd '$ROOT_DIR/apps/api' && uv run pytest -ra"

if [[ -n "${TEST_DATABASE_URL:-}" ]]; then
  echo "Detected TEST_DATABASE_URL; API integration tests will run."
  api_test_cmd="cd '$ROOT_DIR/apps/api' && TEST_DATABASE_URL='$TEST_DATABASE_URL' uv run --locked pytest -ra"
else
  echo "TEST_DATABASE_URL is not set; API integration tests are expected to be skipped."
fi

# Separate-role PostgreSQL tests (ADR 0029 §8). When any role URL is configured, the run is an
# explicit acceptance run: missing or inconsistent role configuration fails instead of skipping.
if [[ -n "${TEST_DATABASE_OWNER_URL:-}${TEST_DATABASE_RUNTIME_URL:-}${TEST_DATABASE_PROVISIONER_URL:-}" ]]; then
  echo "Detected separate-role database URLs; database role tests are required."
  export TEST_DATABASE_OWNER_URL="${TEST_DATABASE_OWNER_URL:-}"
  export TEST_DATABASE_RUNTIME_URL="${TEST_DATABASE_RUNTIME_URL:-}"
  export TEST_DATABASE_PROVISIONER_URL="${TEST_DATABASE_PROVISIONER_URL:-}"
  api_test_cmd="$api_test_cmd --require-database-roles"
fi

run_or_print "Running API tests (apps/api)" "$api_test_cmd" || status=1
run_or_print "Running Web tests (apps/web)" "cd '$ROOT_DIR' && npm --workspace apps/web run test" || status=1

if [[ $status -ne 0 ]]; then
  echo "One or more test suites failed." >&2
  exit $status
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run complete."
else
  echo "All app test suites passed."
fi

