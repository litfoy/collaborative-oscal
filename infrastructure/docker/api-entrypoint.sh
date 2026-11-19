#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Copyright The Collaborative OSCAL Authors.

set -eu

export DEMO_AUTH_SECRET="$(cat /run/demo-credentials/demo-auth-secret)"
export POSTGRES_PASSWORD="$(cat /run/demo-credentials/postgres-password)"
exec "$@"
