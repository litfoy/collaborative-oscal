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
import { DELETE as bffDelete, GET as bff, POST as bffPost, PUT as bffPut } from "@/app/bff/[...path]/route";

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
  it("forwards catalog import bytes without parsing or rewriting them", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(new Response("{}", { headers: { "content-type": "application/json" } }));
    const path = ["tenants", U, "catalogs", U, "import"];
    const input = '{"catalog": {"metadata": {"oscal-version": "1.1.3"}}}';
    const response = await bffPost(new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
      method: "POST", headers: { origin: "http://localhost:3000", "content-type": "application/json" }, body: input,
    }), ctx(path));
    expect(response.status).toBe(200);
    const options = mocks.backendFetch.mock.calls[0][3];
    expect(new TextDecoder().decode(options.body)).toBe(input);
    expect(options.timeoutMs).toBe(120_000);
  });

  it("accepts catalog bodies larger than the profile mutation limit", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(new Response("{}", { headers: { "content-type": "application/json" } }));
    const path = ["tenants", U, "catalogs", "import"];
    const input = " ".repeat(5_401_489);
    const response = await bffPost(new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
      method: "POST", headers: { origin: "http://localhost:3000", "content-type": "application/json" }, body: input,
    }), ctx(path));
    expect(response.status).toBe(200);
    expect(mocks.backendFetch.mock.calls[0][3].body.byteLength).toBe(input.length);
  });
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

  it("proxies profile mutations only for same-origin, allowlisted requests", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(
      new Response(JSON.stringify({ id: U }), { headers: { "content-type": "application/json" } }),
    );
    const path = ["tenants", U, "profiles"];
    const denied = await bffPost(
      new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
        method: "POST",
        headers: {
          origin: "https://evil.example",
          "content-type": "application/json",
        },
        body: JSON.stringify({ title: "Not sent" }),
      }),
      ctx(path),
    );
    expect(denied.status).toBe(403);
    expect(mocks.backendFetch).not.toHaveBeenCalled();

    const response = await bffPost(
      new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
        method: "POST",
        headers: {
          origin: "http://localhost:3000",
          "sec-fetch-site": "same-origin",
          "content-type": "application/json",
        },
        body: JSON.stringify({ title: "Allowed" }),
      }),
      ctx(path),
    );
    expect(response.status).toBe(200);
    expect(mocks.backendFetch).toHaveBeenCalledWith(
      session,
      `/api/v1/${path.join("/")}`,
      undefined,
      { method: "POST", body: JSON.stringify({ title: "Allowed" }) },
    );

    const wrongMethod = await bffPut(
      new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
        method: "PUT",
        headers: { origin: "http://localhost:3000", "content-type": "application/json" },
        body: "{}",
      }),
      ctx(path),
    );
    expect(wrongMethod.status).toBe(404);
  });

  it("allows tenant-scoped mapping collection writes and empty delete responses", async () => {
    mocks.readSession.mockResolvedValue(session);
    const path = ["tenants", U, "mapping-collections"];
    mocks.backendFetch.mockResolvedValue(new Response(JSON.stringify({ id: U }), {
      headers: { "content-type": "application/json" },
    }));
    const created = await bffPost(
      new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
        method: "POST",
        headers: { origin: "http://localhost:3000", "content-type": "application/json" },
        body: JSON.stringify({ title: "Mappings" }),
      }),
      ctx(path),
    );
    expect(created.status).toBe(200);
    expect(mocks.backendFetch.mock.calls[0][1]).toBe(`/api/v1/${path.join("/")}`);

    mocks.backendFetch.mockResolvedValue(new Response(null, { status: 204 }));
    const deletePath = [...path, U];
    const removed = await bffDelete(
      new NextRequest(`http://localhost:3000/bff/${deletePath.join("/")}`, {
        method: "DELETE",
        headers: { origin: "http://localhost:3000", "content-type": "application/json" },
        body: "{}",
      }),
      ctx(deletePath),
    );
    expect(removed.status).toBe(204);
    expect(await removed.text()).toBe("");
  });

  it("proxies related-control lookups using the exact revision and original control ID", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(new Response('{"items":[]}', {
      headers: { "content-type": "application/json" },
    }));
    const path = ["tenants", U, "catalogs", U, "revisions", U, "controls", "AC-1", "related-mappings"];
    const response = await bff(new NextRequest(`http://localhost:3000/bff/${path.join("/")}`), ctx(path));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ items: [] });
    expect(mocks.backendFetch).toHaveBeenCalledWith(
      session,
      `/api/v1/${path.join("/")}`,
      expect.any(URLSearchParams),
    );
  });

  it("preserves the export download header from the authorized API", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(new Response('{"mapping-collection":{}}', {
      headers: {
        "content-type": "application/json",
        "content-disposition": `attachment; filename="mapping-collection-${U}.json"`,
      },
    }));
    const path = ["tenants", U, "mapping-collections", U, "export"];
    const response = await bff(new NextRequest(`http://localhost:3000/bff/${path.join("/")}`), ctx(path));
    expect(response.status).toBe(200);
    expect(response.headers.get("content-disposition")).toBe(
      `attachment; filename="mapping-collection-${U}.json"`,
    );
  });

  it("allows the revision-pinned profile browser through the authenticated proxy", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(
      new Response('{"nodes":[]}', { headers: { "content-type": "application/json" } }),
    );
    const path = ["tenants", U, "catalogs", U, "revisions", U, "profile-browser"];
    const response = await bff(new NextRequest(`http://localhost:3000/bff/${path.join("/")}`), ctx(path));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ nodes: [] });
    expect(mocks.backendFetch).toHaveBeenCalledWith(session, `/api/v1/${path.join("/")}`, expect.any(URLSearchParams));
  });

  it("accepts large explicit selections but still enforces a bounded mutation body", async () => {
    mocks.readSession.mockResolvedValue(session);
    mocks.backendFetch.mockResolvedValue(
      new Response("{}", { headers: { "content-type": "application/json" } }),
    );
    const path = ["tenants", U, "profiles"];
    const request = (body: string) => new NextRequest(`http://localhost:3000/bff/${path.join("/")}`, {
      method: "POST",
      headers: { origin: "http://localhost:3000", "content-type": "application/json" },
      body,
    });
    const body = JSON.stringify({ title: "Large scope", control_ids: Array.from({ length: 10_000 }, (_, i) => `control-${i}`) });
    expect(body.length).toBeGreaterThan(16_384);
    expect((await bffPost(request(body), ctx(path))).status).toBe(200);
    mocks.backendFetch.mockClear();
    expect((await bffPost(request(" ".repeat(3 * 1024 * 1024 + 1)), ctx(path))).status).toBe(413);
    expect(mocks.backendFetch).not.toHaveBeenCalled();
  });
});
