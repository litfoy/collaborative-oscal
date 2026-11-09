import { describe, expect, it } from "vitest";

import { filterBffQuery, isAllowedBffPath } from "@/lib/bff-allowlist";
import { classifyHref, renderProse, safeReturnTo } from "@/lib/safe";

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
    expect(renderProse("Review {{ insert: param, p1 }} and {{ insert: param, p2 }}", { p1: "frequency" })).toBe(
      "Review [frequency] and [p2]",
    );
    expect(renderProse("<script>x</script>", {})).toBe("<script>x</script>");
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

  it("drops unknown query parameters", () => {
    const filtered = filterBffQuery(new URLSearchParams("q=a&limit=5&access_token=x&x=1"));
    expect(filtered.toString()).toBe("q=a&limit=5");
  });
});
