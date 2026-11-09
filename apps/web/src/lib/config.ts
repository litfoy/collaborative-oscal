import "server-only";

export interface WebConfig {
  appUrl: URL;
  secureCookies: boolean;
  issuer: URL;
  clientId: string;
  clientSecret: string | undefined;
  scopes: string;
  authorizationParams: Record<string, string>;
  sessionSecret: string;
  sessionMaxAgeSeconds: number;
  apiBaseUrl: string;
  allowInsecureIssuer: boolean;
}

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

function required(env: NodeJS.ProcessEnv, name: string): string {
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

export function parseConfig(env: NodeJS.ProcessEnv): WebConfig {
  const production = env.NODE_ENV === "production";
  const appUrl = parseUrl("APP_PUBLIC_URL", required(env, "APP_PUBLIC_URL"));
  const issuer = parseUrl("OIDC_ISSUER_URL", required(env, "OIDC_ISSUER_URL"));
  const apiBaseUrl = required(env, "API_BASE_URL").replace(/\/+$/, "");
  parseUrl("API_BASE_URL", apiBaseUrl);

  const sessionSecret = required(env, "SESSION_SECRET");
  if (sessionSecret.length < 32) {
    throw new Error("SESSION_SECRET must be at least 32 characters.");
  }

  const appIsLocal = LOCAL_HOSTS.has(appUrl.hostname);
  if (appUrl.protocol !== "https:" && production && !appIsLocal) {
    throw new Error("APP_PUBLIC_URL must use https in production.");
  }
  if (appUrl.protocol !== "https:" && appUrl.protocol !== "http:") {
    throw new Error("APP_PUBLIC_URL must use http(s).");
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

export function resetConfigForTests(): void {
  cached = undefined;
}
