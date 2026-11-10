# ADR 0007: Browser authentication through a Next.js BFF and a read-only Catalog Explorer API

- **Status:** Accepted
- **Date:** 2026-11-09

## Context

Task 005 adds the first user-facing feature: a read-only catalog explorer. The
browser must authenticate against the configured OIDC provider without holding
tokens, and FastAPI must keep verifying access tokens independently (ADR 0006).

## Decision

### Browser authentication

- **Backend-for-Frontend.** The Next.js server is the OIDC relying party. It
  runs the Authorization Code flow with PKCE (S256), `state` and `nonce` using
  `openid-client` v6 (a maintained, certified OpenID Connect client). No OAuth
  or OIDC protocol handling is implemented by hand. Tokens are verified by the
  library; cookie encryption uses `jose` (JWE `dir` + `A256GCM`).
- **Why not Auth.js.** Auth.js (`next-auth` v5) remains a beta line, its
  session callbacks encourage placing tokens in the client-readable session
  object, and refresh handling is left to the application. A small,
  explicit BFF over `openid-client` gives a smaller token exposure boundary and
  provider-neutral configuration.
- **Sessions are encrypted, stateless, HttpOnly cookies** (chunked,
  `SameSite=Lax`, `Secure` and the `__Host-` prefix on https). The project has
  no session store and this task must not add one. Keys are derived with HKDF
  from `SESSION_SECRET`, with separate purposes for the session and the
  short-lived login-flow cookie.
- **Token exposure.** Access, refresh and ID tokens live only inside the
  encrypted cookie and server memory. They are never rendered into HTML, never
  returned by `/bff`, and never stored in `localStorage` or client state. The
  ID token is kept only for RP-initiated logout (`id_token_hint`). Only the
  access token is sent to FastAPI, which validates issuer, audience, signature
  and token type exactly as before.
- **Refresh.** `proxy.ts` refreshes the access token before it expires
  (single-flight per session) and clears sessions that cannot be refreshed or
  that exceed the absolute lifetime (`SESSION_MAX_AGE_SECONDS`, default 8 h).
- **CSRF and redirects.** Login is a GET that only starts a flow. Logout is a
  POST with an `Origin` check. The `/bff` proxy is GET-only, allowlisted by
  path and query and rejects cross-site `Sec-Fetch-Site`. `returnTo` accepts
  only same-site relative paths. The callback URL is fixed by
  `APP_PUBLIC_URL`. Production requires https for the app and issuer (http is
  accepted only for `localhost`).
- **Known limitation of stateless cookies.** A session cookie cannot be revoked
  server-side. Logout deletes the cookie and revokes the refresh token at the
  provider and ends the provider session, but a copied cookie remains usable
  until the short access-token lifetime elapses and refresh fails. If immediate
  server-side revocation is required, move to a server-side store in a later ADR.

### Catalog API

- Read-only endpoints under `/api/v1/tenants/{tenant_id}/catalogs…` require a
  verified token, a known identity, an active membership and `catalog:read`.
  Non-members (including for non-existent tenants) get an identical 403;
  resources missing inside an authorized tenant get 404. All queries are scoped
  by tenant ID and join through the catalog's tenant, so cross-tenant IDs never
  resolve.
- `GET /api/v1/tenants` lists only tenants with active membership.
- Browsing uses the relational group/control projections. Hierarchy is loaded
  lazily one level at a time (`/outline`). Full OSCAL documents are returned only
  by the explicit immutable-revision export endpoint; control detail is otherwise
  extracted from revision JSONB (via `packages/oscal/control_view.py`) without
  mutation. Free-text OSCAL content is returned as inert strings; the UI renders
  it as text and only allows `http`, `https` and `mailto` links.
- The stable control reference for future Profile Composition is
  `catalog_id + revision_id + oscal_control_id`.
- Search is `ILIKE` on control ID/title with escaped wildcards, bounded
  pagination (`API_PAGE_SIZE_DEFAULT=50`, max 200), deterministic ordering and
  supporting indexes. This is adequate for catalogs of several thousand
  controls; `pg_trgm` is the planned upgrade if needed.

### Revision lifecycle conflict

Imports currently create `draft` revisions and no publish workflow exists. The
explorer therefore lists every revision with its lifecycle label and the API
exposes a `lifecycle_status` filter, rather than hiding all imported content.
Revisions remain immutable. A publish workflow will tighten this later.

## Consequences

- The browser never holds credentials and FastAPI stays the only authority for
  tenant authorization; frontend checks are usability only.
- Operators must provide `SESSION_SECRET` and the provider client configuration.
- Cookie-session revocation is bounded by token lifetimes (see above).
