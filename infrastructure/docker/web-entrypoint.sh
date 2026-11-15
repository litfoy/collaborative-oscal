#!/bin/sh
set -eu

export DEMO_AUTH_SECRET="$(cat /run/demo-credentials/demo-auth-secret)"
exec "$@"
