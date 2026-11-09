// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parseConfig } from "@/lib/config";
import {
  applyMutations,
  flowCookie,
  readFlow,
  readSession,
  sessionCookieMutations,
  type CookieOptions,
} from "@/lib/session";
import { chunk, seal, unseal, type SessionData } from "@/lib/session-crypto";

import { TEST_SECRET, stubWebEnv } from "./env";

const now = () => Math.floor(Date.now() / 1000);

function session(overrides: Partial<SessionData> = {}): SessionData {
  return {
    sub: "user-1",
    name: "Alice",
    accessToken: "ACCESS-TOKEN-" + "a".repeat(2500),
    accessTokenExpiresAt: now() + 300,
    refreshToken: "REFRESH-TOKEN-" + "r".repeat(1500),
    idToken: "ID-TOKEN-" + "i".repeat(2000),
    expiresAt: now() + 3600,
    ...overrides,
  };
}

function jar(values: Record<string, string>) {
  return { get: (name: string) => (name in values ? { value: values[name] } : undefined) };
}

async function roundTrip(data: SessionData) {
  const mutations = await sessionCookieMutations(jar({}), data);
  const store: Record<string, string> = {};
  for (const mutation of mutations) if (mutation.value) store[mutation.name] = mutation.value;
  return { mutations, store };
}

beforeEach(() => stubWebEnv());
afterEach(() => vi.unstubAllEnvs());

describe("session cookies", () => {
  it("round-trips a session across chunked HttpOnly cookies without exposing tokens", async () => {
    const data = session();
    const { mutations, store } = await roundTrip(data);
    const written = mutations.filter((mutation) => mutation.value);
    expect(written.length).toBeGreaterThan(1);
    for (const mutation of written) {
      expect(mutation.value.length).toBeLessThan(4000);
      const options: CookieOptions = mutation.options;
      expect(options.httpOnly).toBe(true);
      expect(options.sameSite).toBe("lax");
      expect(options.path).toBe("/");
      expect(mutation.value).not.toContain("ACCESS-TOKEN");
      expect(mutation.value).not.toContain("REFRESH-TOKEN");
    }
    expect(await readSession(jar(store))).toEqual(data);
  });

  it("uses a __Host- prefixed Secure cookie for https deployments", async () => {
    stubWebEnv({ APP_PUBLIC_URL: "https://app.example.com" });
    const { mutations } = await roundTrip(session());
    expect(mutations[0].name).toBe("__Host-co_session.0");
    expect(mutations[0].options.secure).toBe(true);
  });

  it("rejects tampered, expired, or foreign-key cookies", async () => {
    const { store } = await roundTrip(session());
    const tampered = { ...store, "co_session.0": store["co_session.0"].slice(0, -3) + "AAA" };
    expect(await readSession(jar(tampered))).toBeNull();

    const expired = await roundTrip(session({ expiresAt: now() - 5 }));
    expect(await readSession(jar(expired.store))).toBeNull();

    stubWebEnv({ SESSION_SECRET: "another-secret-another-secret-another-secret" });
    expect(await readSession(jar(store))).toBeNull();
  });

  it("does not accept a login-flow cookie as a session (purpose separation)", async () => {
    const sealed = await seal({ ...session() }, TEST_SECRET, "flow", 60);
    expect(await unseal(sealed, TEST_SECRET, "session")).toBeNull();
  });

  it("clears every chunk on logout", async () => {
    const { store } = await roundTrip(session());
    const mutations = await sessionCookieMutations(jar(store), null);
    expect(mutations.every((mutation) => mutation.value === "" && mutation.options.maxAge === 0)).toBe(true);
    const written: string[] = [];
    applyMutations({ set: (name: string) => written.push(name) }, mutations);
    expect(written).toContain("co_session.0");
  });

  it("stores login flow state encrypted", async () => {
    const mutation = await flowCookie({ state: "s", nonce: "n", codeVerifier: "VERIFIER-SECRET", returnTo: "/x" });
    expect(mutation.value).not.toContain("VERIFIER-SECRET");
    expect(await readFlow(jar({ [mutation.name]: mutation.value }))).toMatchObject({ state: "s", returnTo: "/x" });
  });

  it("chunks deterministically", () => {
    expect(chunk("abcdef", 4)).toEqual(["abcd", "ef"]);
    expect(chunk("")).toEqual([""]);
  });
});

describe("configuration", () => {
  const base = {
    APP_PUBLIC_URL: "https://app.example.com",
    OIDC_ISSUER_URL: "https://idp.example.com/realms/x",
    WEB_OIDC_CLIENT_ID: "c",
    SESSION_SECRET: TEST_SECRET,
    API_BASE_URL: "https://api.example.com",
  };

  it("requires a strong session secret", () => {
    expect(() => parseConfig({ ...base, SESSION_SECRET: "short" } as unknown as NodeJS.ProcessEnv)).toThrow(/32/);
  });

  it("requires https for the app and issuer in production", () => {
    const production = { ...base, NODE_ENV: "production" };
    expect(() => parseConfig({ ...production, APP_PUBLIC_URL: "http://app.example.com" } as unknown as NodeJS.ProcessEnv)).toThrow(/https/);
    expect(() => parseConfig({ ...production, OIDC_ISSUER_URL: "http://idp.example.com" } as unknown as NodeJS.ProcessEnv)).toThrow(/https/);
    expect(parseConfig(production as unknown as NodeJS.ProcessEnv).secureCookies).toBe(true);
  });

  it("refuses to override protocol parameters", () => {
    expect(() =>
      parseConfig({ ...base, WEB_OIDC_AUTHORIZATION_PARAMS: '{"state":"x"}' } as unknown as NodeJS.ProcessEnv),
    ).toThrow(/state/);
    expect(
      parseConfig({ ...base, WEB_OIDC_AUTHORIZATION_PARAMS: '{"audience":"api"}' } as unknown as NodeJS.ProcessEnv)
        .authorizationParams,
    ).toEqual({ audience: "api" });
  });
});
