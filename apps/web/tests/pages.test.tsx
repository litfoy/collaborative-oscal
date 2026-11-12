import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/errors";

import { CATALOG, REVISION, TENANT, catalog, control, groupAc, page, revision } from "./fixtures";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  requireSession: vi.fn(),
  listTenants: vi.fn(),
  listCatalogs: vi.fn(),
  getCatalog: vi.fn(),
  listRevisions: vi.fn(),
  getRevision: vi.fn(),
  getOutline: vi.fn(),
  getControl: vi.fn(),
  redirect: vi.fn((target: string) => {
    throw new Error(`REDIRECT:${target}`);
  }),
}));

vi.mock("@/lib/auth", () => ({ getSession: mocks.getSession, requireSession: mocks.requireSession }));
vi.mock("@/lib/api", () => ({
  listTenants: mocks.listTenants,
  listCatalogs: mocks.listCatalogs,
  getCatalog: mocks.getCatalog,
  listRevisions: mocks.listRevisions,
  getRevision: mocks.getRevision,
  getOutline: mocks.getOutline,
  getControl: mocks.getControl,
}));
vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn() }),
}));

import HomePage from "@/app/page";
import CatalogPage from "@/app/t/[tenantId]/catalogs/[catalogId]/page";
import CatalogsPage from "@/app/t/[tenantId]/catalogs/page";
import TenantLayout from "@/app/t/[tenantId]/layout";

const session = { sub: "u", name: "Alice", accessToken: "t", accessTokenExpiresAt: 9e9, expiresAt: 9e9 };
const tenant = (id: string, name: string) => ({ id, name, slug: name.toLowerCase(), role: "viewer", permissions: ["catalog:read"] });

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getSession.mockResolvedValue(session);
  mocks.requireSession.mockResolvedValue(session);
  mocks.listTenants.mockResolvedValue({ items: [tenant(TENANT, "Alpha")] });
});

describe("home / tenant selection", () => {
  it("requires authentication and offers sign-in", async () => {
    mocks.getSession.mockResolvedValue(null);
    render(await HomePage({ searchParams: Promise.resolve({ reason: "expired", returnTo: "//evil.example" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/session has ended/i);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/auth/login?returnTo=%2F");
    expect(mocks.listTenants).not.toHaveBeenCalled();
  });

  it("lists only the tenants returned by the API when there are several", async () => {
    mocks.listTenants.mockResolvedValue({ items: [tenant("a", "Alpha"), tenant("b", "Beta")] });
    render(await HomePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Choose a workspace" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alpha" })).toHaveAttribute("href", "/t/a/catalogs");
    expect(screen.getByRole("link", { name: "Beta" })).toBeInTheDocument();
    expect(screen.queryByText("Gamma")).toBeNull();
  });

  it("goes straight to a single authorized tenant", async () => {
    mocks.listTenants.mockResolvedValue({ items: [tenant(TENANT, "Alpha")] });
    await expect(HomePage({ searchParams: Promise.resolve({}) })).rejects.toThrow(`REDIRECT:/t/${TENANT}/catalogs`);
  });

  it("explains when the user has no workspace", async () => {
    mocks.listTenants.mockResolvedValue({ items: [] });
    render(await HomePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText(/do not have access to any workspace/i)).toBeInTheDocument();
  });

  it("shows an expired-session state when the API rejects the token", async () => {
    mocks.listTenants.mockRejectedValue(new ApiError("session_expired", 401, "x"));
    render(await HomePage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/session has expired/i);
    expect(screen.getByRole("link", { name: /sign in again/i })).toBeInTheDocument();
  });
});

describe("tenant layout", () => {
  it("denies an unauthorized tenant without calling any catalog API", async () => {
    mocks.listTenants.mockResolvedValue({ items: [tenant("a", "Alpha")] });
    render(await TenantLayout({ children: <p>SECRET</p>, params: Promise.resolve({ tenantId: TENANT }) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/do not have access/i);
    expect(screen.queryByText("SECRET")).toBeNull();
  });

  it("renders the shell with sign-out and tenant switching for authorized tenants", async () => {
    mocks.listTenants.mockResolvedValue({ items: [tenant(TENANT, "Alpha"), tenant("b", "Beta")] });
    render(await TenantLayout({ children: <p>CONTENT</p>, params: Promise.resolve({ tenantId: TENANT }) }));
    expect(screen.getByText("CONTENT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" }).closest("form")).toHaveAttribute("method", "post");
    expect(screen.getByRole("link", { name: "Switch workspace" })).toBeInTheDocument();
  });
});

describe("catalog overview", () => {
  const params = Promise.resolve({ tenantId: TENANT });

  it("renders multiple catalogs with origin, revisions and control counts", async () => {
    mocks.listCatalogs.mockResolvedValue(
      page([
        catalog(),
        catalog({ id: "c2", name: "Internal Baseline", origin_type: "custom", source_organization: null, revision_count: 3, latest_revision: revision({ revision_number: 3, control_count: 120 }) }),
      ]),
    );
    render(await CatalogsPage({ params, searchParams: Promise.resolve({}) }));
    const list = screen.getByRole("list", { name: "Catalogs" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Imported")).toBeInTheDocument();
    expect(within(list).getByText("Internally authored")).toBeInTheDocument();
    expect(within(list).getByText("120")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "Sample Security Practices" })).toHaveAttribute("href", `/t/${TENANT}/catalogs/${CATALOG}`);
    expect(screen.getByText(/own licence terms/i)).toBeInTheDocument();
  });

  it("shows empty states and passes the search term through", async () => {
    mocks.listCatalogs.mockResolvedValue(page([]));
    render(await CatalogsPage({ params, searchParams: Promise.resolve({}) }));
    expect(screen.getByText(/no catalogs yet/i)).toBeInTheDocument();
    render(await CatalogsPage({ params, searchParams: Promise.resolve({ q: "nist" }) }));
    expect(screen.getByText(/No catalogs match/)).toBeInTheDocument();
    expect(mocks.listCatalogs).toHaveBeenLastCalledWith(TENANT, { q: "nist", limit: 12, offset: 0 }, expect.any(String));
  });

  it("paginates", async () => {
    mocks.listCatalogs.mockResolvedValue({ items: [catalog()], total: 30, limit: 12, offset: 12 });
    render(await CatalogsPage({ params, searchParams: Promise.resolve({ page: "2" }) }));
    expect(mocks.listCatalogs).toHaveBeenLastCalledWith(TENANT, expect.objectContaining({ offset: 12 }), expect.any(String));
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", expect.stringContaining("page=3"));
    expect(screen.getByRole("link", { name: "Previous" })).toBeInTheDocument();
  });

  it("surfaces API errors", async () => {
    mocks.listCatalogs.mockRejectedValue(new ApiError("forbidden", 403, "x"));
    render(await CatalogsPage({ params, searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Access denied/);
  });

  it("only offers import to members with catalog import permission", async () => {
    mocks.listCatalogs.mockResolvedValue(page([]));
    const { unmount } = render(await CatalogsPage({ params, searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("button", { name: "Import catalog" })).not.toBeInTheDocument();
    unmount();
    mocks.listTenants.mockResolvedValue({ items: [{ ...tenant(TENANT, "Alpha"), permissions: ["catalog:read", "catalog:import"] }] });
    render(await CatalogsPage({ params, searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("button", { name: "Import catalog" })).toBeInTheDocument();
  });
});

describe("catalog details", () => {
  const params = Promise.resolve({ tenantId: TENANT, catalogId: CATALOG });
  const second = revision({ id: "rev-2", revision_number: 2, lifecycle_status: "draft", source_version: "1.1.0", control_count: 7 });

  beforeEach(() => {
    mocks.getCatalog.mockResolvedValue(catalog({ revision_count: 2 }));
    mocks.listRevisions.mockResolvedValue(page([second, revision()]));
    mocks.getRevision.mockImplementation(async (_t: string, _c: string, id: string) => ({
      ...(id === "rev-2" ? second : revision()),
      group_count: 3,
      source_document: { title: null, version: null, last_modified: null, published: null },
    }));
    mocks.getOutline.mockResolvedValue(page([groupAc]));
    vi.stubGlobal("fetch", vi.fn());
  });

  it("defaults to the latest revision and lists the revision history", async () => {
    render(await CatalogPage({ params, searchParams: Promise.resolve({}) }));
    expect(mocks.getRevision).toHaveBeenCalledWith(TENANT, CATALOG, "rev-2", expect.any(String));
    expect(screen.getByLabelText("Revision")).toHaveValue("rev-2");
    expect(screen.getByRole("option", { name: /Revision 1/ })).toBeInTheDocument();
    expect(screen.getByText(/7 controls in 3 groups/)).toBeInTheDocument();
    expect(screen.getByRole("treeitem", { name: /Access Control/ })).toBeInTheDocument();
  });

  it("honours a requested revision and ignores unknown ones", async () => {
    render(await CatalogPage({ params, searchParams: Promise.resolve({ revision: REVISION }) }));
    expect(mocks.getRevision).toHaveBeenLastCalledWith(TENANT, CATALOG, REVISION, expect.any(String));
    render(await CatalogPage({ params, searchParams: Promise.resolve({ revision: "unknown" }) }));
    expect(mocks.getRevision).toHaveBeenLastCalledWith(TENANT, CATALOG, "rev-2", expect.any(String));
  });

  it("opens a requested revision outside the first page of history", async () => {
    mocks.listRevisions.mockResolvedValue(page([second]));
    render(await CatalogPage({ params, searchParams: Promise.resolve({ revision: REVISION }) }));
    expect(mocks.getRevision).toHaveBeenCalledWith(TENANT, CATALOG, REVISION, expect.any(String));
    expect(screen.getByLabelText("Revision")).toHaveValue(REVISION);
  });

  it("preloads a deep-linked control and tolerates a missing one", async () => {
    mocks.getControl.mockResolvedValueOnce(control());
    render(await CatalogPage({ params, searchParams: Promise.resolve({ control: "ac-1" }) }));
    expect(screen.getByRole("heading", { level: 1, name: /ac-1/ })).toBeInTheDocument();
    mocks.getControl.mockRejectedValueOnce(new ApiError("not_found", 404, "x"));
    render(await CatalogPage({ params, searchParams: Promise.resolve({ control: "gone" }) }));
    expect(screen.getAllByText(/select a control/i).length).toBeGreaterThan(0);
  });

  it("reports a missing catalog", async () => {
    mocks.getCatalog.mockRejectedValue(new ApiError("not_found", 404, "x"));
    render(await CatalogPage({ params, searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Not found/);
  });
});
