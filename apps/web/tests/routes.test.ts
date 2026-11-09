// @vitest-environment node
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stubWebEnv } from "./env";

const mocks = vi.hoisted(() => ({
  endSession: vi.fn(),
  beginAuthorization: vi.fn(),
  readSession: vi.fn(),
  backendFetch: vi.fn(),
  cookies: vi.fn(),
}));

vi.mock("@/lib/oidc", () => ({ endSession: mocks.endSession, beginAuthorization: mocks.beginAuthorization }));
vi.mock("@/lib/api", () => ({ backendFetch: mocks.backendFetch }));
vi.mock("next/headers", () => ({ cookies: mocks.cookies }));
vi.mock("@/lib/session", async (original) => ({
  ...(await original<typeof import("@/lib/session")>()),
  readSession: mocks.readSession,
}));

import { GET as login } from "@/app/auth/login/route";
import { POST as logout } from "@/app/auth/logout/route";
import { GET as bff } from "@/app/bff/[...path]/route";

const session = { sub: "u", accessToken: "SECRET-TOKEN", idToken: "ID", accessTokenExpiresAt: 9e9, expiresAt: 9e9 };
const U = "11111111-1111-4111-8111-111111111111";
const PATH = ["tenants", U, "catalogs"];
const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });

beforeEach(() => {
  vi.clearAllMocks();
  stubWebEnv();
  mocks.cookies.mockResolvedValue({});
});

describe("logout", () => {
  it("rejects cross-origin requests without touching the session", async () => {
    const res = await logout(new NextRequest("http://localhost:3000/auth/logout", { method: "POST", headers: { origin: "https://evil.example" } }));
    expect(res.status).toBe(403);
    expect(mocks.endSession).not.toHaveBeenCalled();
  });

  it("revokes the session, clears cookies and redirects to the provider", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.endSession.mockResolvedValue(new URL("http://localhost:8080/realms/test/logout"));
    const res = await logout(
      new NextRequest("http://localhost:3000/auth/logout", {
        method: "POST",
        headers: { origin: "http://localhost:3000", cookie: "co_session.0=abc; co_session.1=def" },
      }),
    );
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("http://localhost:8080/realms/test/logout");
    expect(mocks.endSession).toHaveBeenCalledWith(session);
    const cleared = res.headers.getSetCookie().join(";");
    expect(cleared).toMatch(/co_session\.0=;/);
    expect(cleared).toMatch(/Max-Age=0|Expires=Thu, 01 Jan 1970/);
  });
});

describe("login", () => {
  it("sanitises returnTo before starting the flow", async () => {
    mocks.beginAuthorization.mockResolvedValue({ url: new URL("http://localhost:8080/auth"), flow: { state: "s", nonce: "n", codeVerifier: "v", returnTo: "/" } });
    await login(new NextRequest("http://localhost:3000/auth/login?returnTo=//evil.example"));
    expect(mocks.beginAuthorization).toHaveBeenCalledWith("/");
  });

  it("falls back to an error page when the provider is down", async () => {
    mocks.beginAuthorization.mockRejectedValue(new Error("down"));
    const res = await login(new NextRequest("http://localhost:3000/auth/login"));
    expect(res.headers.get("location")).toContain("error=provider_unavailable");
  });
});

describe("BFF proxy", () => {
  it("returns 401 without a session and never calls the API", async () => {
    mocks.readSession.mockResolvedValue(null);
    const res = await bff(new NextRequest("http://localhost:3000/bff/"+PATH.join("/")), ctx(PATH));
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: "session_expired" });
    expect(mocks.backendFetch).not.toHaveBeenCalled();
  });

  it("rejects cross-site fetches and non-allowlisted paths", async () => {
    mocks.readSession.mockResolvedValue(session);
    const cross = await bff(new NextRequest("http://localhost:3000/bff/"+PATH.join("/"), { headers: { "sec-fetch-site": "cross-site" } }), ctx(PATH));
    expect(cross.status).toBe(403);
    const other = await bff(new NextRequest("http://localhost:3000/bff/me"), ctx(["me"]));
    expect(other.status).toBe(404);
    expect(mocks.backendFetch).not.toHaveBeenCalled();
  });

  it("proxies allowlisted reads without leaking the token", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(new Response(JSON.stringify({ items: [] }), { headers: { "content-type": "application/json" } }));
    const res = await bff(new NextRequest("http://localhost:3000/bff/"+PATH.join("/")), ctx(PATH));
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).not.toContain("SECRET-TOKEN");
    expect(JSON.stringify([...res.headers])).not.toContain("SECRET-TOKEN");
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("maps upstream 401 to session_expired", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(new Response("{}", { status: 401, headers: { "content-type": "application/json" } }));
    const res = await bff(new NextRequest("http://localhost:3000/bff/"+PATH.join("/")), ctx(PATH));
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: "session_expired" });
  });
});
