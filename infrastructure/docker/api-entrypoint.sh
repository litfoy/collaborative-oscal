#!/bin/sh
set -eu

export DEMO_AUTH_SECRET="$(cat /run/demo-credentials/demo-auth-secret)"
export POSTGRES_PASSWORD="$(cat /run/demo-credentials/postgres-password)"
exec "$@"
