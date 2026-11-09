#!/usr/bin/env bash
# Creates a local development user in the dev realm through the Keycloak admin API.
# Credentials come from the environment so that none are committed:
#   KEYCLOAK_ADMIN_USERNAME, KEYCLOAK_ADMIN_PASSWORD (the bootstrap admin)
#   DEV_USER_NAME, DEV_USER_PASSWORD (the user to create)
set -euo pipefail

: "${KEYCLOAK_ADMIN_USERNAME:?}" "${KEYCLOAK_ADMIN_PASSWORD:?}" "${DEV_USER_NAME:?}" "${DEV_USER_PASSWORD:?}"
BASE="${KEYCLOAK_URL:-http://localhost:8080}"
REALM="${KEYCLOAK_REALM:-collaborative-oscal-dev}"

admin_token=$(curl -fsS "$BASE/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  --data-urlencode "username=$KEYCLOAK_ADMIN_USERNAME" \
  --data-urlencode "password=$KEYCLOAK_ADMIN_PASSWORD" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

payload=$(DEV_USER_NAME="$DEV_USER_NAME" DEV_USER_PASSWORD="$DEV_USER_PASSWORD" python3 - <<'PY'
import json, os
name = os.environ["DEV_USER_NAME"]
print(json.dumps({
    "username": name, "email": f"{name}@example.test", "firstName": "Dev", "lastName": "User",
    "enabled": True, "emailVerified": True,
    "credentials": [{"type": "password", "value": os.environ["DEV_USER_PASSWORD"], "temporary": False}],
}))
PY
)

status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$BASE/admin/realms/$REALM/users" \
  -H "Authorization: Bearer $admin_token" -H 'Content-Type: application/json' -d "$payload")
case "$status" in
  201) echo "Created user $DEV_USER_NAME." ;;
  409) echo "User $DEV_USER_NAME already exists." ;;
  *) echo "Unexpected status $status" >&2; exit 1 ;;
esac

curl -fsS "$BASE/admin/realms/$REALM/users?username=$DEV_USER_NAME&exact=true" \
  -H "Authorization: Bearer $admin_token" |
  python3 -c 'import json,sys; print("Subject (sub):", json.load(sys.stdin)[0]["id"])'
