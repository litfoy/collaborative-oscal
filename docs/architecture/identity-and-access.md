# Identity, authentication, and tenant authorization

## Trust boundaries

The application is an OAuth 2.0 protected resource server. A standards-compliant
OpenID Connect provider authenticates the person and issues an access token for this
API. The API validates the token; it does not implement passwords, login, MFA, or
token issuance. Keycloak is the local reference provider, not a domain dependency.
OIDC issuer, API audience, token profile, signing algorithms, and key retrieval are
deployment configuration.

The `GET /api/v1/me` endpoint requires a validated bearer access token. The API
identifies an application user by the exact `(issuer, subject)` pair, creating or
refreshing that internal identity after successful token verification. Email is
optional profile data and is stored only when the provider marks it verified; it is
never an identity key. No tenant membership is created during login, and `/me`
does not reveal membership or token claims.

## Token profile and key verification

`OIDC_ISSUER_URL` and `OIDC_API_AUDIENCE` are required for protected requests.
`OIDC_ALLOWED_ALGORITHMS` accepts only supported asymmetric algorithms; HMAC and
`none` are rejected. The default local Keycloak profile uses the access-token
payload discriminator `typ=Bearer`. Providers with a different access-token
contract must configure `OIDC_ACCESS_TOKEN_TYPE_CLAIM` and
`OIDC_ACCESS_TOKEN_TYPE_VALUE` to a provider-defined claim that distinguishes
access tokens from ID tokens. Do not select an ID-token claim such as `nonce` as
the only discriminator.

Set `OIDC_ACCESS_TOKEN_PROFILE=rfc9068` for RFC 9068 providers. That profile
requires the `at+jwt` or `application/at+jwt` protected header and the RFC 9068
`client_id`, `iat`, and `jti` claims in addition to standard issuer, audience,
expiration, and subject checks. Generic OIDC providers are not assumed to use the
same JOSE `typ` header; they must instead use a configured payload discriminator
and the API-specific audience.

When `OIDC_JWKS_URL` is unset, the API retrieves OIDC discovery metadata from the
configured issuer and checks that the discovered issuer matches exactly. A
configured or discovered JWKS URL must use the issuer's origin; redirects are not
followed. Neither `jku` nor embedded JWK token headers are accepted. PyJWT verifies
the signature and registered claims. JWKS entries are cached for a bounded
`OIDC_JWKS_CACHE_SECONDS`; unknown key IDs trigger refresh subject to the short
`OIDC_JWKS_REFRESH_COOLDOWN_SECONDS`. Temporary issuer outages fail closed with
503; invalid tokens return 401 without provider details.

The local Keycloak issuer has `typ=Bearer` on access-token claims and an
API-audience mapper that adds `collaborative-oscal-api` to access tokens only.
This intentionally prevents the realm's ID token from being accepted as an API
credential.

## Application identity and memberships

`user_identities` stores the internal UUID, external issuer/subject, optional
display name and verified email, and timestamps. Its unique constraint on
`(issuer, subject)` prevents account ambiguity across providers; email is not
unique. External tokens and refresh tokens are never persisted.

`tenant_memberships` associates one identity with one tenant, a tenant-scoped
role, and active/inactive status. A unique tenant/user constraint prevents
duplicates; foreign keys protect tenant and identity integrity; check constraints
bound role and status values. Inactive memberships grant nothing. Memberships are
looked up from PostgreSQL for each authorization decision, so an administrator's
role or status change takes effect on the next request.

Roles map centrally to explicit permissions:

| Tenant role | Permissions |
|---|---|
| `tenant_admin` | `tenant:read`, `tenant:manage`, `catalog:read`, `catalog:write`, `catalog:import` |
| `catalog_editor` | `tenant:read`, `catalog:read`, `catalog:write`, `catalog:import` |
| `viewer` | `tenant:read`, `catalog:read` |

Unknown roles and missing memberships deny by default. Permissions are tenant
scoped; a role in one tenant says nothing about another tenant or an organizational
subtree. Future roles such as Auditor, Risk Owner, Control Owner, and External
Reviewer can be mapped to permissions without changing token verification.

## Trusted tenant context

Client-selected tenant IDs are selectors only, never proof of access. Future
tenant-scoped routes should declare a path parameter named `tenant_id` and depend
on `require_tenant_permission(...)`. That application boundary resolves the
validated identity, reads the active membership for exactly the requested tenant,
checks the permission through `AuthorizationService`, and returns an
`AuthorizedTenantContext`. It does not read or trust `X-Tenant-ID`, tenant claims,
or a default tenant. Business services remain independent of FastAPI and can keep
their explicit tenant UUID arguments; an HTTP adapter must construct the
authorized context before calling them.

Current protected resources return 403 for an authenticated identity without
membership or permission. Future resources whose existence is sensitive should
consistently translate both nonexistent and unauthorized resource lookups to 404
at that resource boundary. This policy is not needed by the current `/me`
endpoint, which is not tenant scoped.

Background jobs and future automation workers are not implemented. They must use
explicit operator-provisioned service identities and narrowly scoped tenant
permissions, never a user's token, a client-supplied tenant ID, or implicit
administrator access. Machine identity provisioning and audit-event persistence
remain future work. The bootstrap CLI emits a structured local audit log event;
production deployments must route and retain administrative logs appropriately.

## Authentication and authorization sequence

```mermaid
sequenceDiagram
    actor User
    participant IdP as OIDC Identity Provider
    participant API as FastAPI API
    participant JWKS as Trusted issuer discovery/JWKS
    participant DB as PostgreSQL

    User->>IdP: Authenticate using provider flow (not implemented by API)
    IdP-->>User: API access token
    User->>API: GET /api/v1/me with Bearer access token
    API->>JWKS: Load issuer metadata and signing keys from configured origin
    JWKS-->>API: Matching public signing key
    API->>API: Verify signature, issuer, audience, time and access-token profile
    API->>DB: Resolve/create identity by exact issuer + subject
    DB-->>API: Internal UserIdentity
    API-->>User: Safe identity fields only

    User->>API: Future tenant route with selected tenant_id
    API->>DB: Resolve identity's active membership for that tenant
    DB-->>API: Tenant-scoped role/status
    API->>API: Map role to explicit permission; deny by default
    API->>DB: Business service/repository call with authorized tenant context
    API-->>User: Tenant-scoped result or 403/404
```

## Local Keycloak development

1. Copy `.env.example` to `.env`. Choose unique local Keycloak bootstrap admin
   credentials and set `KEYCLOAK_ADMIN_USERNAME` and `KEYCLOAK_ADMIN_PASSWORD`
   only in that ignored local file or your shell environment. Do not commit them.
2. Start the optional local provider and database:

   ```sh
   docker compose --env-file .env -f infrastructure/docker/compose.yaml \
     --profile identity up -d db keycloak
   ```

   The `collaborative-oscal-dev` realm is imported from
   `infrastructure/keycloak/collaborative-oscal-dev-realm.json`. Its public
   `collaborative-oscal-dev` client disables password/direct grants and enables
   PKCE S256 and OAuth 2.0 Device Authorization Grant for local CLI testing.
   Create a development user in this realm using the local Keycloak admin console;
   the imported realm has no default users or passwords.
3. Configure the API from `.env.example` and apply migrations:

   ```sh
   cd apps/api
   uv sync
   uv run alembic -c ../../alembic.ini upgrade head
   uv run uvicorn app.main:app --reload
   ```

4. Request a device code and open the returned verification URI in a browser:

   ```sh
   curl --fail-with-body --data-urlencode \
     'client_id=collaborative-oscal-dev' \
     http://localhost:8080/realms/collaborative-oscal-dev/protocol/openid-connect/auth/device
   ```

   After signing in and approving the device, exchange the device code at
   `/realms/collaborative-oscal-dev/protocol/openid-connect/token` using
   `grant_type=urn:ietf:params:oauth:grant-type:device_code`,
   `client_id=collaborative-oscal-dev`, and the returned `device_code`. Poll
   according to the response interval and keep the access token local:

   ```sh
   curl --fail-with-body --data-urlencode \
     'grant_type=urn:ietf:params:oauth:grant-type:device_code' \
     --data-urlencode 'client_id=collaborative-oscal-dev' \
     --data-urlencode 'device_code=<device-code>' \
     http://localhost:8080/realms/collaborative-oscal-dev/protocol/openid-connect/token
   ```

   Do not use the OAuth password grant.
5. Call `GET http://localhost:8000/api/v1/me` with that access token. It must
   include the configured API audience. If no tenant exists, create one through
   this trusted local application operation:

   ```sh
   cd apps/api
   uv run python -c 'from app.application.services import GrcService; from app.persistence.database import create_unit_of_work_factory; tenant = GrcService(create_unit_of_work_factory()).create_tenant("Example", "example"); print(tenant.id)'
   ```

   Use the external user's Keycloak user ID (the token's `sub`) and configured
   issuer with the local bootstrap command below to add a tenant administrator.
   Bootstrap does not accept a token or create a tenant:

   ```sh
   cd apps/api
   uv run python -m app.cli bootstrap-admin \
     --issuer http://localhost:8080/realms/collaborative-oscal-dev \
     --subject '<verified-subject>' \
     --tenant-id '<existing-tenant-uuid>'
   ```

   Tenant provisioning is not a public API in this iteration. Create the initial
   tenant through a trusted operator-controlled application operation before
   assigning its first administrator. The CLI is idempotent and only accepts the
   configured issuer and an existing tenant.

Run unit authentication and authorization tests with:

```sh
cd apps/api
uv run pytest tests/test_authentication.py tests/test_authorization.py tests/test_identity_api.py
```

PostgreSQL persistence and migration tests require `TEST_DATABASE_URL` for a
dedicated database whose name ends in `_test`; they use local signing fixtures and
do not contact an external identity provider.

## Browser sign-in and catalog access

The Next.js BFF authenticates users with Authorization Code + PKCE and forwards only the access token to FastAPI, which still verifies it independently. `GET /api/v1/tenants` lists active memberships; catalog routes require `catalog:read` in the requested tenant. See [Catalog Explorer](catalog-explorer.md) and ADR 0007.

Profile reads and exports also require `catalog:read`; Profile creation and updates
require `catalog:write`. Both permissions are evaluated against the active
membership in the tenant selected by the request path.
