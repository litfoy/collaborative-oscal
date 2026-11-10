// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";

import { backendFetch } from "@/lib/api";
import type { SessionData } from "@/lib/session-crypto";

import { stubWebEnv } from "./env";

vi.mock("@/lib/auth", () => ({ requireSession: vi.fn() }));

const session: SessionData = {
  sub: "user",
  accessToken: "secret-access-token",
  accessTokenExpiresAt: 9e9,
  expiresAt: 9e9,
};

beforeEach(() => {
  stubWebEnv();
});

describe("backend failure logging", () => {
  it("logs safe connection diagnostics without error messages or credentials", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(
      new TypeError("secret-access-token", {
        cause: Object.assign(new Error("secret-response-body"), { code: "ECONNREFUSED" }),
      }),
    ));

    await expect(backendFetch(session, "/api/v1/tenants", new URLSearchParams({ q: "private-search" })))
      .rejects.toMatchObject({ status: 503, kind: "unavailable" });
    expect(log).toHaveBeenCalledWith("[backend] Request failed", {
      origin: "http://api.test",
      path: "/api/v1/tenants",
      reason: "connection_error",
      code: "ECONNREFUSED",
    });
    expect(JSON.stringify(log.mock.calls)).not.toMatch(/secret-|private-search/);
  });

  it("identifies request timeouts", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("private", "TimeoutError")));
    await expect(backendFetch(session, "/api/v1/tenants")).rejects.toMatchObject({ status: 503 });
    expect(log).toHaveBeenCalledWith("[backend] Request failed", expect.objectContaining({ reason: "timeout" }));
  });

  it("logs HTTP status without consuming or logging the response", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const response = new Response("secret-response-body", { status: 500 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    expect(await backendFetch(session, "/api/v1/tenants")).toBe(response);
    expect(log).toHaveBeenCalledWith("[backend] Unsuccessful response", {
      origin: "http://api.test", path: "/api/v1/tenants", status: 500,
    });
    expect(response.bodyUsed).toBe(false);
    expect(JSON.stringify(log.mock.calls)).not.toContain("secret");
  });

  it("does not log successful requests", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}")));
    await backendFetch(session, "/api/v1/tenants");
    expect(log).not.toHaveBeenCalled();
  });
});
