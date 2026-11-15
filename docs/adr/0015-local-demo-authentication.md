# ADR 0015: Explicit local demo authentication

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

Local demonstrations need to work without an identity provider while retaining
the tenant and permission checks described in ADR 0006 and the browser BFF
boundary in ADR 0007.

## Decision

Keycloak/OIDC remains the default. An explicit `AUTH_MODE=demo` selects a fixed
server-controlled identity. The BFF sends a separately configured 32-byte random
secret, encoded as lowercase hex, in the existing Bearer header. The API compares
it in constant time and does not accept it in Keycloak mode. No provider failure
causes a fallback. The browser never receives this credential or an OIDC session.

An operator runs `python -m app.cli bootstrap-demo` against a dedicated demo
database. Reserved UUIDs and a reserved issuer/subject identify the demo tenant,
identity, and membership. Bootstrap inserts missing rows transactionally and
rejects conflicts without modifying existing records. No business content is
created. The API requires the expected active `catalog_editor` membership, confines
tenant selection and listing to the reserved tenant, and still performs normal
permission checks. Unexpected roles and missing or modified bootstrap records
fail closed.

The demo frontend has no login: anyone who can reach it can act as the demo user.
It must not be public or connected to production data. `APP_PUBLIC_URL` must be a
loopback origin; operators must also bind and firewall the frontend, API, and
database appropriately. `API_BASE_URL` is independently configured on the server
and may name an internal service. URL validation is not network isolation; HTTP
between services must only be used on a protected network. `NODE_ENV` is not a
deployment safety control.

## Consequences

This is a deliberate local-only exception to ADR 0006's OIDC-only authentication,
not a replacement for Keycloak or an additional general-purpose identity provider.
The shared credential must be kept server-only and rotated if exposed. There is no
per-person accountability in demo mode. Switching modes does not migrate data or
grant the demo user access to other tenants.
