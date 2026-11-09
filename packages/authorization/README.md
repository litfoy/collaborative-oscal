# Authorization boundary

The current authentication and authorization implementation lives under
`apps/api/app/authentication`, `apps/api/app/application/authorization.py`, and
`apps/api/app/persistence/identity.py`. This package remains a reserved boundary for
future extraction; it is not a separate service or installed package.

The API verifies provider-neutral OIDC access tokens, maps exact issuer/subject pairs
to internal identities, and resolves active tenant membership and explicit
tenant-scoped permissions from PostgreSQL. Only `GET /api/v1/me` is exposed. There
are no catalog/GRC routes, user-management UI, or machine identities.

See [Identity and access architecture](../../docs/architecture/identity-and-access.md)
for configuration, the trusted tenant-context boundary, and local Keycloak setup.
