import "server-only";

import * as client from "openid-client";

import { getConfig } from "./config";
import type { SessionData } from "./session-crypto";

let configuration: Promise<client.Configuration> | undefined;

export function getOidcConfiguration(): Promise<client.Configuration> {
  if (!configuration) {
    const config = getConfig();
    const pending = client.discovery(
      config.issuer,
      config.clientId,
      config.clientSecret,
      config.clientSecret ? undefined : client.None(),
      config.allowInsecureIssuer ? { execute: [client.allowInsecureRequests] } : undefined,
    );
    pending.catch(() => {
      configuration = undefined;
    });
    configuration = pending;
  }
  return configuration;
}

export function callbackUrl(): URL {
  return new URL("/auth/callback", getConfig().appUrl);
}

export function signedOutUrl(): URL {
  return new URL("/signed-out", getConfig().appUrl);
}

export async function beginAuthorization(returnTo: string) {
  const config = getConfig();
  const oidc = await getOidcConfiguration();
  const codeVerifier = client.randomPKCECodeVerifier();
  const state = client.randomState();
  const nonce = client.randomNonce();
  const url = client.buildAuthorizationUrl(oidc, {
    ...config.authorizationParams,
    redirect_uri: callbackUrl().href,
    scope: config.scopes,
    code_challenge: await client.calculatePKCECodeChallenge(codeVerifier),
    code_challenge_method: "S256",
    state,
    nonce,
  });
  return { url, flow: { state, nonce, codeVerifier, returnTo } };
}

function toSession(tokens: client.TokenEndpointResponse, previous?: SessionData) {
  const config = getConfig();
  const now = Math.floor(Date.now() / 1000);
  const claims = "id_token" in tokens && tokens.id_token ? decodeClaims(tokens.id_token) : null;
  const expiresIn = typeof tokens.expires_in === "number" ? tokens.expires_in : 300;
  const session: SessionData = {
    sub: claims?.sub ?? previous?.sub ?? "",
    name: claims?.name ?? previous?.name,
    email: claims?.email ?? previous?.email,
    accessToken: tokens.access_token,
    accessTokenExpiresAt: now + expiresIn,
    refreshToken: tokens.refresh_token ?? previous?.refreshToken,
    idToken: tokens.id_token ?? previous?.idToken,
    expiresAt: previous?.expiresAt ?? now + config.sessionMaxAgeSeconds,
  };
  return session;
}

function decodeClaims(
  idToken: string,
): { sub?: string; name?: string; email?: string } | null {
  // The ID token was already validated by openid-client; it is only used for display claims.
  try {
    const payload = idToken.split(".")[1];
    return JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
  } catch {
    return null;
  }
}

export async function completeAuthorization(
  callback: URL,
  flow: { state: string; nonce: string; codeVerifier: string },
): Promise<SessionData> {
  const oidc = await getOidcConfiguration();
  const tokens = await client.authorizationCodeGrant(oidc, callback, {
    pkceCodeVerifier: flow.codeVerifier,
    expectedState: flow.state,
    expectedNonce: flow.nonce,
    idTokenExpected: true,
  });
  const claims = tokens.claims();
  const session = toSession(tokens);
  session.sub = claims?.sub ?? session.sub;
  if (!session.sub) {
    throw new Error("The identity provider did not return a subject.");
  }
  return session;
}

const inflight = new Map<string, Promise<SessionData | null>>();

/**
 * Refreshes the access token. Concurrent refreshes for the same refresh token share
 * one request, because providers commonly rotate (and invalidate) refresh tokens.
 */
export function refreshSession(session: SessionData): Promise<SessionData | null> {
  const refreshToken = session.refreshToken;
  if (!refreshToken) return Promise.resolve(null);
  const existing = inflight.get(refreshToken);
  if (existing) return existing;
  const pending = (async () => {
    try {
      const oidc = await getOidcConfiguration();
      const tokens = await client.refreshTokenGrant(oidc, refreshToken);
      return toSession(tokens, session);
    } catch {
      return null;
    } finally {
      setTimeout(() => inflight.delete(refreshToken), 15_000).unref?.();
    }
  })();
  inflight.set(refreshToken, pending);
  return pending;
}

export async function endSession(session: SessionData): Promise<URL> {
  const fallback = signedOutUrl();
  try {
    const oidc = await getOidcConfiguration();
    if (session.refreshToken) {
      await client
        .tokenRevocation(oidc, session.refreshToken, { token_type_hint: "refresh_token" })
        .catch(() => undefined);
    }
    if (!oidc.serverMetadata().end_session_endpoint) return fallback;
    const parameters: Record<string, string> = {
      post_logout_redirect_uri: fallback.href,
      client_id: getConfig().clientId,
    };
    if (session.idToken) parameters.id_token_hint = session.idToken;
    return client.buildEndSessionUrl(oidc, parameters);
  } catch {
    return fallback;
  }
}
