# ADR 0006: Use provider-neutral OIDC identities and tenant-scoped RBAC

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

The API needs an authentication boundary and tenant authorization foundation
without coupling the GRC domain to an identity provider. The service is
self-hostable, must support open identity standards, and must not accept client
tenant selectors as proof of authorization. Local passwords and tokens must not
become application-managed credentials.

## Decision

- Treat FastAPI as an OAuth 2.0 protected resource server. Use OpenID Connect
  discovery and signed JWT access tokens; the identity provider authenticates
  users. Do not store passwords or OIDC access/refresh tokens.
- Use PyJWT with cryptographic support to verify signatures and required issuer,
  API audience, expiration, optional not-before, subject, configured asymmetric
  algorithms, and the configured access-token profile. Never use an ID token as
  an API credential. RFC 9068 uses its `at+jwt` JOSE type and required claims;
  other providers must configure an access-token-specific payload discriminator.
- Retrieve discovery/JWKS documents only from the configured issuer origin or an
  explicitly configured same-origin JWKS endpoint. Do not follow redirects or
  use token-provided key URLs. Bound response size and request time, cache keys
  with a bounded lifetime, and refresh unknown key IDs with a short cooldown.
- Keep Keycloak as an optional local reference provider. Do not add Keycloak
  concepts or dependencies to application/domain models; compatible providers
  are selected only through configuration.
- Persist internal identities by unique `(issuer, subject)`, not email. Persist
  active/inactive tenant memberships in PostgreSQL with unique tenant/user
  constraints, foreign keys, and constrained roles.
- Map tenant roles to explicit permissions in one authorization service. Check
  membership and permission for each request and construct a trusted tenant
  context before calling tenant-scoped business services. Deny by default.
- Expose only a minimal authenticated `/api/v1/me` endpoint in this iteration.
  Do not auto-create memberships at login, accept tenant headers as trusted
  context, or add a public user-registration or GRC API.

## Consequences

The API can use Keycloak or another provider with an OIDC-compliant discovery
document and JWT access tokens that meet the configured profile. Providers with
nonstandard claim layouts require explicit environment configuration and tests;
the API intentionally does not guess whether arbitrary JWTs are access tokens.
Tenant membership changes take effect on the next database-backed authorization
check. The local Keycloak realm uses a dedicated API audience and device flow for
developer CLI access; it does not enable password grants.

Tenant-scoped GRC routes, login UI, organization-level authorization, machine
identity provisioning, persistent audit events, RLS, and full user management
remain out of scope. See [Identity and access](../architecture/identity-and-access.md)
for configuration, bootstrap, and operational details.
