// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { describe, expect, it, vi } from "vitest";

import { bffGet, bffWrite } from "@/lib/bff-client";

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("bff client conflict classification", () => {
  it("classifies structured stale_update conflicts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: "stale_update",
              plan_id: "11111111-1111-4111-8111-111111111111",
              expected_version: 1,
              current_version: 2,
            },
          },
          409,
        ),
      ),
    );

    await expect(bffWrite("POST", "tenants/x/assessment-plans/y/versions", {})).rejects.toMatchObject({
      kind: "stale_update",
      status: 409,
    });
  });

  it("falls back to generic conflict when the code is unknown", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            detail: {
              code: "different_conflict",
            },
          },
          409,
        ),
      ),
    );

    await expect(bffWrite("POST", "tenants/x/assessment-plans/y/versions", {})).rejects.toMatchObject({
      kind: "conflict",
      status: 409,
    });
  });

  it("falls back to generic conflict when no structured detail is present", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ error: "unavailable" }, 409)),
    );

    await expect(bffWrite("POST", "tenants/x/assessment-plans/y/versions", {})).rejects.toMatchObject({
      kind: "conflict",
      status: 409,
    });
  });

  it("serializes repeated query parameters for profile selections", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }, 200));
    vi.stubGlobal("fetch", fetchMock);

    await bffGet("tenants/x/systems/y/compliance-explorer", {
      profile_id: ["p1", "p2"],
      limit: 20,
      offset: 0,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/bff/tenants/x/systems/y/compliance-explorer?profile_id=p1&profile_id=p2&limit=20&offset=0",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });
});



