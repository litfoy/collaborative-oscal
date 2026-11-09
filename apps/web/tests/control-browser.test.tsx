import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ControlBrowser } from "@/components/ControlBrowser";

import { CATALOG, REVISION, TENANT, ac1, ac11, ac2, control, groupAc, groupIr, jsonResponse, page } from "./fixtures";

const base = `/bff/tenants/${TENANT}/catalogs/${CATALOG}/revisions/${REVISION}`;

function mockApi(overrides: Record<string, () => Response> = {}) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    for (const [fragment, factory] of Object.entries(overrides)) {
      if (url.includes(fragment)) return factory();
    }
    if (url.includes("/outline") && url.includes("parent_id=g-ac")) return jsonResponse(page([ac1, ac2, { ...ac1, id: "x", kind: "group", oscal_id: "ac-priv", title: "Privileged", child_count: 0 }]));
    if (url.includes("/outline") && url.includes("parent_id=c-ac1")) return jsonResponse(page([ac11]));
    if (url.includes("/controls/ac-2")) return jsonResponse(control({ oscal_control_id: "ac-2", title: "Account Management" }));
    if (url.includes("/controls/ac-1.1")) return jsonResponse(control({ oscal_control_id: "ac-1.1", title: "Policy Exceptions" }));
    if (url.includes("/controls/ac-1")) return jsonResponse(control());
    if (url.includes("/controls?")) {
      const q = new URL(url, "http://x").searchParams.get("q");
      if (q === "zzz") return jsonResponse(page([]));
      return jsonResponse(page([{ id: "c-ac2", oscal_control_id: "ac-2", title: "Account Management", parent_control_id: null, group: { id: "g-ac", oscal_group_id: "ac", title: "Access Control" }, reference: { catalog_id: CATALOG, revision_id: REVISION, oscal_control_id: "ac-2" } }]));
    }
    return jsonResponse({}, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function renderBrowser(initialControl = null as ReturnType<typeof control> | null) {
  return render(
    <ControlBrowser
      tenantId={TENANT}
      catalogId={CATALOG}
      revisionId={REVISION}
      initialRoot={page([groupAc, groupIr])}
      initialControl={initialControl}
    />,
  );
}

beforeEach(() => {
  vi.stubGlobal("scrollTo", vi.fn());
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ControlBrowser", () => {
  it("shows root groups and an empty detail state without loading everything", () => {
    const calls = mockApi();
    renderBrowser();
    expect(screen.getByRole("tree", { name: /control hierarchy/i })).toBeInTheDocument();
    expect(screen.getAllByRole("treeitem")).toHaveLength(2);
    expect(screen.getByText(/select a control/i)).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("lazily expands nested groups and controls and shows control details", async () => {
    const user = userEvent.setup();
    const calls = mockApi();
    renderBrowser();

    await user.click(screen.getByRole("treeitem", { name: /Access Control/ }));
    expect(await screen.findByRole("treeitem", { name: /ac-1.*Access Policy/ })).toBeInTheDocument();
    expect(calls.some((url) => url.includes("parent_kind=group") && url.includes("parent_id=g-ac"))).toBe(true);
    expect(screen.getByRole("treeitem", { name: /Access Control/ })).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("treeitem", { name: /ac-1.*Access Policy/ }));
    expect(await screen.findByRole("heading", { level: 1, name: /ac-1\s*Access Policy/ })).toBeInTheDocument();
    expect(await screen.findByRole("treeitem", { name: /ac-1\.1/ })).toBeInTheDocument();
    expect(screen.getByText(/Review every \[frequency\]\./)).toBeInTheDocument();
    expect(screen.getByText(/Source:/)).toHaveTextContent("Sample Security Practices");

    await user.click(screen.getByRole("treeitem", { name: /ac-1\.1/ }));
    expect(await screen.findByRole("heading", { level: 1, name: /ac-1\.1/ })).toBeInTheDocument();
    expect(calls.some((url) => url.includes(`${base}/controls/ac-1.1`))).toBe(true);
  });

  it("supports keyboard navigation", async () => {
    const user = userEvent.setup();
    mockApi();
    renderBrowser();
    const first = screen.getByRole("treeitem", { name: /Access Control/ });
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("treeitem", { name: /Incident Response/ })).toHaveFocus();
    await user.keyboard("{ArrowUp}{ArrowRight}");
    expect(await screen.findByRole("treeitem", { name: /ac-2/ })).toBeInTheDocument();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("treeitem", { name: /ac-1.*Access Policy/ })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(first).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(first).toHaveAttribute("aria-expanded", "false");
    await user.keyboard("{End}");
    expect(screen.getByRole("treeitem", { name: /Incident Response/ })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(first).toHaveFocus();
    await user.keyboard("{ArrowRight}{ArrowRight}{Enter}");
    expect(await screen.findByRole("heading", { level: 1, name: /ac-1/ })).toBeInTheDocument();
  });

  it("searches controls and opens a result", async () => {
    const user = userEvent.setup();
    const calls = mockApi();
    renderBrowser();
    await user.type(screen.getByRole("searchbox", { name: /search controls/i }), "account{Enter}");
    const results = await screen.findByRole("region", { name: /search results/i });
    expect(within(results).getByText(/1 control match/)).toBeInTheDocument();
    expect(calls.some((url) => url.includes("q=account"))).toBe(true);
    await user.click(within(results).getByRole("button", { name: /ac-2/ }));
    expect(await screen.findByRole("heading", { level: 1 })).toBeInTheDocument();

    await user.clear(screen.getByRole("searchbox"));
    await user.type(screen.getByRole("searchbox"), "zzz{Enter}");
    expect(await screen.findByText(/No controls match/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByRole("tree")).toBeInTheDocument();
  });

  it("reports expired sessions with a sign-in link", async () => {
    const user = userEvent.setup();
    mockApi({ "/outline": () => jsonResponse({ error: "session_expired" }, 401) });
    renderBrowser();
    await user.click(screen.getByRole("treeitem", { name: /Access Control/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/session has expired/i);
    expect(within(alert).getByRole("link", { name: /sign in again/i })).toHaveAttribute("href", "/auth/login");
  });

  it("reports API errors without leaving stale details", async () => {
    const user = userEvent.setup();
    mockApi({ "/controls/ac-1": () => jsonResponse({ detail: "x" }, 404) });
    renderBrowser();
    await user.click(screen.getByRole("treeitem", { name: /Access Control/ }));
    await user.click(await screen.findByRole("treeitem", { name: /ac-1.*Access Policy/ }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/could not be found/i));
  });

  it("reports network failures", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("network"))));
    renderBrowser();
    await user.click(screen.getByRole("treeitem", { name: /Access Control/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unavailable/i);
  });

  it("renders an initial control from the server", () => {
    mockApi();
    renderBrowser(control());
    expect(screen.getByRole("heading", { level: 1, name: /ac-1/ })).toBeInTheDocument();
  });
});
