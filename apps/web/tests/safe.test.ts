// @vitest-environment node
import { describe, expect, it } from "vitest";

import { filterBffQuery, isAllowedBffPath, isAllowedBffRequest } from "@/lib/bff-allowlist";
import { classifyHref, parameterText, renderProse, safeReturnTo } from "@/lib/safe";
import type { Parameter } from "@/lib/types";

const UUID = "11111111-2222-3333-4444-555555555555";

describe("safeReturnTo", () => {
  it.each([
    ["/t/abc/catalogs?q=x", "/t/abc/catalogs?q=x"],
    ["/", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["https://evil.example/", "/"],
    ["javascript:alert(1)", "/"],
    ["/auth/logout", "/"],
    ["/bff/tenants", "/"],
    ["/ok\r\nSet-Cookie: x=1", "/"],
    ["", "/"],
    [null, "/"],
  ])("%s -> %s", (input, expected) => {
    expect(safeReturnTo(input)).toBe(expected);
  });
});

describe("classifyHref", () => {
  it("allows only inert schemes", () => {
    expect(classifyHref("https://example.com/a")).toEqual({ kind: "external", href: "https://example.com/a" });
    expect(classifyHref("mailto:a@example.com").kind).toBe("external");
    expect(classifyHref("#res-1").kind).toBe("internal");
    for (const bad of ["javascript:alert(1)", " JavaScript:alert(1)", "data:text/html,<b>", "vbscript:x", "/relative", "//host/x"]) {
      expect(classifyHref(bad).kind).toBe("blocked");
    }
  });
});

describe("renderProse", () => {
  it("replaces parameter insertions and leaves markup as text", () => {
    expect(renderProse("Review {{ insert: param, p1 }} and {{ insert: param, p2 }}", new Map([["p1", "[frequency]"]]))).toBe(
      "Review [frequency] and [p2]",
    );
    expect(renderProse("<script>x</script>", new Map())).toBe("<script>x</script>");
  });

  it("uses assigned values, follows parameter references, and never chooses unassigned options", () => {
    const parameter = (id: string, overrides: Partial<Parameter> = {}): Parameter => ({
      id, values: [], props: [], links: [], constraints: [], guidelines: [], ...overrides,
    });
    const parameters = [
      parameter("gc.1.1-prm1", { label: "frequency", values: ["annually"] }),
      parameter("multi", { values: ["first", "second"] }),
      parameter("nested", { values: ["Review {{ insert: param, gc.1.1-prm1 }}"] }),
      parameter("unassigned", { label: "review period", select: { choices: ["monthly", "yearly"] } }),
      parameter("unlabelled"),
      parameter("self", { values: ["{{ insert: param, self }}"] }),
      parameter("cycle-a", { values: ["{{ insert: param, cycle-b }}"] }),
      parameter("cycle-b", { values: ["{{ insert: param, cycle-a }}"] }),
      parameter("hostile", { values: ["<script>alert(1)</script>"] }),
      parameter("__proto__", { values: ["literal parameter value"] }),
    ];
    const original = JSON.stringify(parameters);
    const text = parameterText(parameters);
    expect(renderProse("{{ insert: param, gc.1.1-prm1 }}", text)).toBe("annually");
    expect(text.get("multi")).toBe("first, second");
    expect(text.get("nested")).toBe("Review annually");
    expect(text.get("unassigned")).toBe("[review period]");
    expect(text.get("unlabelled")).toBe("[unlabelled]");
    expect(text.get("self")).toBe("[self]");
    expect(text.get("cycle-a")).not.toContain("{{");
    expect(text.get("cycle-b")).not.toContain("{{");
    expect(text.get("hostile")).toBe("<script>alert(1)</script>");
    expect(renderProse("{{ insert: param, unknown }} {{ insert: param, constructor }}", text)).toBe("[unknown] [constructor]");
    expect(text.get("__proto__")).toBe("literal parameter value");
    expect(JSON.stringify(parameters)).toBe(original);
  });
});

describe("BFF allowlist", () => {
  it("allows only read-only catalog paths", () => {
    expect(isAllowedBffPath(["tenants", UUID, "catalogs"])).toBe(true);
    expect(isAllowedBffPath(["tenants", UUID, "catalogs", UUID, "revisions", UUID, "outline"])).toBe(true);
    expect(isAllowedBffPath(["tenants", UUID, "catalogs", UUID, "revisions", UUID, "controls", "ac-1.1"])).toBe(true);
    expect(isAllowedBffPath(["me"])).toBe(false);
    expect(isAllowedBffPath(["tenants", UUID, "catalogs", "..", "x"])).toBe(false);
    expect(isAllowedBffPath(["tenants", UUID, "catalogs", UUID, "revisions", UUID, "controls", "a/b"])).toBe(false);
    expect(isAllowedBffPath(["tenants", "not-a-uuid", "catalogs"])).toBe(false);
  });

  it("allows only explicit Profile methods and paths", () => {
    const profiles = ["tenants", UUID, "profiles"];
    const profile = [...profiles, UUID];
    expect(isAllowedBffRequest(profiles, "GET")).toBe(true);
    expect(isAllowedBffRequest(profiles, "POST")).toBe(true);
    expect(isAllowedBffRequest(profile, "GET")).toBe(true);
    expect(isAllowedBffRequest(profile, "PUT")).toBe(true);
    expect(isAllowedBffRequest([...profile, "export"], "GET")).toBe(true);
    expect(isAllowedBffRequest([...profile, "export"], "PUT")).toBe(false);
    expect(isAllowedBffRequest(["tenants", UUID, "catalogs"], "POST")).toBe(false);
    expect(isAllowedBffRequest(profile, "DELETE")).toBe(false);
  });

  it("drops unknown query parameters", () => {
    const filtered = filterBffQuery(new URLSearchParams("q=a&limit=5&access_token=x&x=1"));
    expect(filtered.toString()).toBe("q=a&limit=5");
  });
});
