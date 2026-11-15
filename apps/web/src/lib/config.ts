import "server-only";

interface CommonConfig {
  appUrl: URL;
  secureCookies: boolean;
  apiBaseUrl: string;
}

export interface KeycloakConfig extends CommonConfig {
  authMode: "keycloak";
  issuer: URL;
  clientId: string;
  clientSecret: string | undefined;
  scopes: string;
  authorizationParams: Record<string, string>;
  sessionSecret: string;
  sessionMaxAgeSeconds: number;
  allowInsecureIssuer: boolean;
}

export interface DemoConfig extends CommonConfig {
  authMode: "demo";
  demoAuthSecret: string;
}

export type WebConfig = KeycloakConfig | DemoConfig;

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

function required(env: Readonly<Record<string, string | undefined>>, name: string): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable ${name}.`);
  }
  return value;
}

function parseUrl(name: string, value: string): URL {
  try {
    return new URL(value);
  } catch {
    throw new Error(`${name} must be an absolute URL.`);
  }
}

function parseAuthorizationParams(raw: string | undefined): Record<string, string> {
  if (!raw?.trim()) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("WEB_OIDC_AUTHORIZATION_PARAMS must be a JSON object of strings.");
  }
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed) ||
    !Object.values(parsed).every((value) => typeof value === "string")
  ) {
    throw new Error("WEB_OIDC_AUTHORIZATION_PARAMS must be a JSON object of strings.");
  }
  const params = parsed as Record<string, string>;
  const reserved = [
    "client_id",
    "redirect_uri",
    "response_type",
    "state",
    "nonce",
    "code_challenge",
    "code_challenge_method",
    "scope",
  ];
  for (const key of reserved) {
    if (key in params) {
      throw new Error(`WEB_OIDC_AUTHORIZATION_PARAMS must not override ${key}.`);
    }
  }
  return params;
}

export function parseConfig(env: Readonly<Record<string, string | undefined>>): WebConfig {
  const production = env.NODE_ENV === "production";
  const authMode = env.AUTH_MODE ?? "keycloak";
  if (authMode !== "keycloak" && authMode !== "demo") {
    throw new Error("AUTH_MODE must be keycloak or demo.");
  }
  const appUrl = parseUrl("APP_PUBLIC_URL", required(env, "APP_PUBLIC_URL"));
  const apiBaseUrl = required(env, "API_BASE_URL").replace(/\/+$/, "");
  const apiUrl = parseUrl("API_BASE_URL", apiBaseUrl);

  const appIsLocal = LOCAL_HOSTS.has(appUrl.hostname);
  if (appUrl.protocol !== "https:" && production && !appIsLocal) {
    throw new Error("APP_PUBLIC_URL must use https in production.");
  }
  if (appUrl.protocol !== "https:" && appUrl.protocol !== "http:") {
    throw new Error("APP_PUBLIC_URL must use http(s).");
  }
  if (authMode === "demo") {
    if (!appIsLocal) throw new Error("Demo APP_PUBLIC_URL must be loopback.");
    if (appUrl.username || appUrl.password || appUrl.pathname !== "/" || appUrl.search || appUrl.hash) {
      throw new Error("Demo APP_PUBLIC_URL must be an origin without credentials.");
    }
    if (!["http:", "https:"].includes(apiUrl.protocol) || apiUrl.username || apiUrl.password || apiUrl.search || apiUrl.hash) {
      throw new Error("Demo API_BASE_URL must be an HTTP(S) URL without credentials, query, or fragment.");
    }
    const demoAuthSecret = required(env, "DEMO_AUTH_SECRET");
    if (!/^[0-9a-f]{64}$/.test(demoAuthSecret)) {
      throw new Error("DEMO_AUTH_SECRET must be 32 random bytes encoded as lowercase hex.");
    }
    return { authMode, appUrl, secureCookies: appUrl.protocol === "https:", apiBaseUrl, demoAuthSecret };
  }

  const issuer = parseUrl("OIDC_ISSUER_URL", required(env, "OIDC_ISSUER_URL"));
  const sessionSecret = required(env, "SESSION_SECRET");
  if (sessionSecret.length < 32) {
    throw new Error("SESSION_SECRET must be at least 32 characters.");
  }

  const issuerIsLocal = LOCAL_HOSTS.has(issuer.hostname);
  if (issuer.protocol !== "https:" && !(issuer.protocol === "http:" && issuerIsLocal)) {
    throw new Error("OIDC_ISSUER_URL must use https (http is only allowed for localhost).");
  }

  const maxAge = Number(env.SESSION_MAX_AGE_SECONDS ?? "28800");
  if (!Number.isInteger(maxAge) || maxAge < 60 || maxAge > 7 * 24 * 3600) {
    throw new Error("SESSION_MAX_AGE_SECONDS must be an integer between 60 and 604800.");
  }

  return {
    authMode,
    appUrl,
    secureCookies: appUrl.protocol === "https:",
    issuer,
    clientId: required(env, "WEB_OIDC_CLIENT_ID"),
    clientSecret: env.WEB_OIDC_CLIENT_SECRET?.trim() || undefined,
    scopes: env.WEB_OIDC_SCOPES?.trim() || "openid profile email offline_access",
    authorizationParams: parseAuthorizationParams(env.WEB_OIDC_AUTHORIZATION_PARAMS),
    sessionSecret,
    sessionMaxAgeSeconds: maxAge,
    apiBaseUrl,
    allowInsecureIssuer: issuer.protocol === "http:",
  };
}

let cached: WebConfig | undefined;

export function getConfig(): WebConfig {
  cached ??= parseConfig(process.env);
  return cached;
}

export function getKeycloakConfig(): KeycloakConfig {
  const config = getConfig();
  if (config.authMode !== "keycloak") throw new Error("OIDC is unavailable in demo mode.");
  return config;
}

export function resetConfigForTests(): void {
  cached = undefined;
}
