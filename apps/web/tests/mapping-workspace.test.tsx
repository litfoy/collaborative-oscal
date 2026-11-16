import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MappingWorkspace } from "@/components/MappingWorkspace";
import type { MappingCollection } from "@/lib/types";
import { catalog, control, jsonResponse, revision } from "./fixtures";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const collection: MappingCollection = {
  id: "collection-1",
  tenant_id: "tenant-1",
  title: "Policy relationships",
  description: "",
  oscal_version: "1.2.3",
  oscal_document_uuid: "document-1",
  version: "1.0.0",
  mappings: [{
    id: "mapping-1",
    source_catalog_id: "catalog-1",
    source_revision_id: "revision-1",
    target_catalog_id: "catalog-2",
    target_revision_id: "revision-2",
    entries: [{
      id: "entry-1",
      relationship: "equivalent-to",
      matching_rationale: "semantic",
      justification: "",
      sources: [
        { type: "control", "id-ref": "AC-1" },
        { type: "control", control_id: "AC-2" },
      ],
      targets: [{ type: "control", id_ref: "POL-1" }],
    }],
  }],
  created_by: "user-1",
  updated_by: "user-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const emptyCollection: MappingCollection = {
  ...collection,
  mappings: collection.mappings.map((pair) => ({ ...pair, entries: [] })),
};
const editableCatalogs = [
  catalog({ id: "catalog-1", name: "Access Baseline", latest_revision: revision({ id: "revision-1", catalog_id: "catalog-1" }) }),
  catalog({ id: "catalog-2", name: "Security Standard", latest_revision: revision({ id: "revision-2", catalog_id: "catalog-2", revision_number: 2, source_version: "2025" }) }),
];

function installWorkspaceFetch() {
  const sourceNodes = [
    { key: "/catalog/groups/access", parent_key: null, kind: "group", id: "access", title: "Access controls", text: "", properties: [] },
    { key: "/catalog/groups/access/controls/ac-1", parent_key: "/catalog/groups/access", kind: "control", id: "AC-1", title: "Access Control Policy", text: "Review access annually.", properties: [] },
    { key: "/catalog/groups/accounts", parent_key: null, kind: "group", id: "accounts", title: "Account management", text: "", properties: [] },
    { key: "/catalog/groups/accounts/controls/ac-2", parent_key: "/catalog/groups/accounts", kind: "control", id: "AC-2", title: "Account Management", text: "Authorize account changes.", properties: [] },
  ];
  const targetNodes = [
    { key: "/catalog/groups/policies", parent_key: null, kind: "group", id: "policies", title: "Policies", text: "", properties: [] },
    { key: "/catalog/groups/policies/controls/pol-1", parent_key: "/catalog/groups/policies", kind: "control", id: "POL-1", title: "Security Policy", text: "Document security requirements.", properties: [] },
    { key: "/catalog/groups/policies/controls/pol-2", parent_key: "/catalog/groups/policies", kind: "control", id: "POL-2", title: "Risk Policy", text: "Review risks.", properties: [] },
  ];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("profile-browser")) {
      return jsonResponse({ nodes: url.includes("catalog-1") ? sourceNodes : targetNodes });
    }
    if (url.includes("/revisions?")) {
      const rev = url.includes("catalog-1")
        ? revision({ id: "revision-1", catalog_id: "catalog-1" })
        : revision({ id: "revision-2", catalog_id: "catalog-2", revision_number: 2, source_version: "2025" });
      return jsonResponse({ items: [rev], total: 1, limit: 200, offset: 0 });
    }
    if (url.includes("/controls/")) {
      const isTarget = url.includes("catalog-2");
      return jsonResponse(control({
        oscal_control_id: isTarget ? "POL-1" : "AC-1",
        title: isTarget ? "Security Policy" : "Access Control Policy",
        parts: [{
          id: "statement", name: "statement", prose: "The normative requirement text.",
          props: [], links: [], parts: [],
        }],
      }));
    }
    if (init?.method === "PUT") return jsonResponse({ detail: "Unable to save mapping collection." }, 500);
    return jsonResponse({ items: [], total: 0, limit: 200, offset: 0 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("MappingWorkspace", () => {
  it("displays control IDs with their catalog control names", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const data = url.includes("profile-browser")
        ? {
          nodes: [{
            key: "control-1",
            parent_key: null,
            kind: "control",
            id: url.includes("catalog-1") ? "AC-1" : "POL-1",
            title: url.includes("catalog-1") ? "Access Control Policy" : "Security Policy",
            text: "",
            properties: [],
          }],
        }
        : { items: [], total: 0, limit: 200, offset: 0 };
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }));

    render(
      <MappingWorkspace
        tenantId="tenant-1"
        catalogs={[]}
        catalogTotal={0}
        canWrite={false}
        initialCollection={collection}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText((_, element) => element?.textContent === "AC-1 — Access Control Policy")).toBeInTheDocument();
      expect(screen.getByText((_, element) => element?.textContent === "POL-1 — Security Policy")).toBeInTheDocument();
    });
    expect(screen.getByRole("searchbox", { name: /Search source/ })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: /AC-1/ })).toBeDisabled();
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });

  it("keeps source and target selections independent through search, requires a relationship, and supports entry editing", async () => {
    installWorkspaceFetch();
    const user = userEvent.setup();
    render(<MappingWorkspace tenantId="tenant-1" catalogs={editableCatalogs} catalogTotal={2}
      canWrite initialCollection={emptyCollection} />);

    await screen.findByRole("checkbox", { name: /AC-1 Access Control Policy/ });
    const sourceSearch = screen.getByRole("searchbox", { name: /Search source/ });
    await user.click(screen.getAllByText("View full control definition")[0]);
    expect(await screen.findAllByText("The normative requirement text.")).not.toHaveLength(0);
    await user.click(screen.getByRole("checkbox", { name: /AC-1 Access Control Policy/ }));
    expect(screen.getByText("Unsaved changes", { selector: "[role=status]" })).toBeInTheDocument();
    const section = screen.getByLabelText(/Catalog section · Source/);
    await user.selectOptions(section, "/catalog/groups/accounts");
    expect(screen.queryByRole("checkbox", { name: /AC-1 Access Control Policy/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Selected source.*control \(1\)/)).toBeInTheDocument();
    await user.selectOptions(section, "");
    expect(await screen.findByRole("checkbox", { name: /AC-1 Access Control Policy/ })).toBeChecked();
    await user.type(sourceSearch, "unmatched term");
    expect(screen.queryByRole("checkbox", { name: /AC-1 Access Control Policy/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Selected source.*control \(1\)/)).toBeInTheDocument();
    await user.clear(sourceSearch);
    expect(await screen.findByRole("checkbox", { name: /AC-1 Access Control Policy/ })).toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: /AC-2 Account Management/ }));
    await user.click(screen.getByRole("checkbox", { name: /POL-1 Security Policy/ }));

    const addButton = screen.getByRole("button", { name: "Add mapping entry" });
    expect(addButton).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Relationship"), "subset-of");
    expect(addButton).toBeEnabled();
    expect(screen.getByText("Source set is a subset of Target set (subset-of)")).toBeInTheDocument();
    await user.click(addButton);
    expect(screen.getByText("Source set (2)")).toBeInTheDocument();
    expect(screen.getByText("Target set (1)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByText("Editing existing mapping entry")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Relationship"), "superset-of");
    await user.type(screen.getByLabelText("Justification"), "Updated comparison.");
    await user.click(screen.getByRole("button", { name: "Update mapping entry" }));
    expect(screen.getByText("Source set is a superset of Target set (superset-of)")).toBeInTheDocument();
    expect(screen.getByText("Updated comparison.")).toBeInTheDocument();
  });

  it("warns before adding a duplicate mapping when control selection order differs", async () => {
    installWorkspaceFetch();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();
    render(<MappingWorkspace tenantId="tenant-1" catalogs={editableCatalogs} catalogTotal={2}
      canWrite initialCollection={collection} />);

    await screen.findByRole("checkbox", { name: /AC-1 Access Control Policy/ });
    await user.click(screen.getByRole("checkbox", { name: /AC-2 Account Management/ }));
    await user.click(screen.getByRole("checkbox", { name: /AC-1 Access Control Policy/ }));
    await user.click(screen.getByRole("checkbox", { name: /POL-1 Security Policy/ }));
    await user.selectOptions(screen.getByLabelText("Relationship"), "equivalent-to");
    await user.click(screen.getByRole("button", { name: "Add mapping entry" }));

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("identical mapping entry"));
    expect(screen.getByText("Mapping entries (1)")).toBeInTheDocument();
  });

  it("keeps draft content and reports save errors without duplicate submission", async () => {
    const fetchMock = installWorkspaceFetch();
    const realFetch = fetchMock.getMockImplementation();
    if (!realFetch) throw new Error("Workspace fetch mock is unavailable.");
    const saveRequest: { resolve?: (response: Response) => void } = {};
    fetchMock.mockImplementation((input, init) => init?.method === "PUT"
      ? new Promise<Response>((resolve) => { saveRequest.resolve = resolve; })
      : realFetch(input, init));
    const user = userEvent.setup();
    render(<MappingWorkspace tenantId="tenant-1" catalogs={editableCatalogs} catalogTotal={2}
      canWrite initialCollection={collection} />);

    const title = screen.getByRole("textbox", { name: "Collection title" });
    await user.clear(title);
    await user.type(title, "Revised mapping");
    expect(screen.getByText("Unsaved changes", { selector: "[role=status]" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    const savingButton = await screen.findByRole("button", { name: "Saving…" });
    expect(savingButton).toBeDisabled();
    await user.click(savingButton);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT")).toHaveLength(1);
    if (!saveRequest.resolve) throw new Error("Save request was not started.");
    saveRequest.resolve(jsonResponse({ detail: "Unable to save mapping collection." }, 500));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save mapping collection.");
    expect(title).toHaveValue("Revised mapping");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });
});
