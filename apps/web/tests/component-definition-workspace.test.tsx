import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { ComponentDefinitionWorkspace } from "@/components/ComponentDefinitionWorkspace";
import { MeasureDetailWorkspace } from "@/components/MeasureDetailWorkspace";
import type { ComponentDefinition } from "@/lib/types";
import { catalog, control, page, revision, TENANT } from "./fixtures";

const mocks = vi.hoisted(() => ({ bffGet: vi.fn(), bffWrite: vi.fn(), push: vi.fn() }));
vi.mock("@/lib/bff-client", () => mocks);
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));

const CATALOG = "22222222-2222-4222-8222-222222222222";
const REVISION = "33333333-3333-4333-8333-333333333333";
const SECOND_REVISION = "33333333-3333-4333-8333-333333333334";
const DOCUMENT = "44444444-4444-4444-8444-444444444444";
const COMPONENT = "55555555-5555-4555-8555-555555555555";
const OTHER_COMPONENT = "55555555-5555-4555-8555-555555555556";
const selectedCatalog = catalog({ id: CATALOG, name: "Security", latest_revision: revision({ id: REVISION, catalog_id: CATALOG }) });
const created: ComponentDefinition = {
  id: DOCUMENT, tenant_id: TENANT, title: "Security document",
  oscal_document_uuid: "66666666-6666-4666-8666-666666666666", oscal_version: "1.2.3", version: "1.0.0",
  components: [{
    id: COMPONENT, oscal_uuid: "77777777-7777-4777-8777-777777777777", type: "policy",
    title: "Multifactor authentication", description: "Protect privileged access.", requirements: [],
  }, {
    id: OTHER_COMPONENT, oscal_uuid: "77777777-7777-4777-8777-777777777778", type: "software",
    title: "Audit logging", description: "Collect audit events.", requirements: [],
  }],
  created_by: "88888888-8888-4888-8888-888888888888", updated_by: "88888888-8888-4888-8888-888888888888",
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.bffGet.mockImplementation(async (path: string) => {
    if (path.endsWith("/revisions")) return page([
      revision({ id: REVISION, catalog_id: CATALOG }),
      revision({ id: SECOND_REVISION, catalog_id: CATALOG, revision_number: 2 }),
    ]);
    if (path.endsWith("/profile-browser")) return { nodes: [
      { key: "ac-1", parent_key: null, kind: "control", id: "ac-1", title: "Access Policy", text: "policy requirements", properties: [{ name: "sec_level", value: "high" }] },
      { key: "ac-2", parent_key: null, kind: "control", id: "ac-2", title: "Account Management", text: "accounts", properties: [{ name: "sec_level", value: "low" }] },
    ] };
    if (path.endsWith("/related-mappings")) return { items: [{
      collection_id: "collection", collection_title: "Advisory mapping", mapping_uuid: "mapping", entry_uuid: "entry",
      relationship: "equivalent-to", matching_rationale: "semantic", matched_side: "source",
      sources: [{ catalog_id: CATALOG, catalog_name: "Security", revision_id: REVISION, revision_number: 1, control_id: "ac-1", title: "Access Policy" }],
      targets: [{ catalog_id: CATALOG, catalog_name: "Security", revision_id: SECOND_REVISION, revision_number: 2, control_id: "ac-2", title: "Account Management" }],
    }] };
    if (path.endsWith("/controls/ac-1")) return control();
    if (path.includes("/revisions/")) return { ...revision({ id: REVISION, catalog_id: CATALOG }), group_count: 0, source_document: {} };
    return page([]);
  });
});

it("searches descriptions, filters types, and links each component to its workspace", async () => {
  const user = userEvent.setup();
  render(<ComponentDefinitionWorkspace tenantId={TENANT} initialDefinitions={[created]} definitionTotal={1}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  expect(screen.queryByLabelText("Measure title")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Audit logging" })).toHaveAttribute("href", `/t/${TENANT}/measures/${DOCUMENT}/${OTHER_COMPONENT}`);
  await user.type(screen.getByLabelText("Search measures"), "privileged");
  expect(screen.getByRole("link", { name: "Multifactor authentication" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Audit logging" })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Component type"), "software");
  expect(screen.getByText("No measures match these filters.")).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Search measures"));
  expect(screen.getByRole("link", { name: "Audit logging" })).toBeInTheDocument();
});

it("creates a measure and navigates to its component", async () => {
  mocks.bffWrite.mockResolvedValue(created);
  const user = userEvent.setup();
  render(<ComponentDefinitionWorkspace tenantId={TENANT} initialDefinitions={[]} definitionTotal={0}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  await user.click(screen.getByRole("button", { name: "New measure" }));
  await user.type(screen.getByLabelText("Measure title"), "Multifactor authentication");
  await user.type(screen.getByLabelText("Reusable description"), "Protect privileged access.");
  await user.click(screen.getByRole("button", { name: "Create measure" }));
  expect(mocks.bffWrite).toHaveBeenCalledWith("POST", `tenants/${TENANT}/component-definitions`, {
    title: "Multifactor authentication", type: "policy", description: "Protect privileged access.", requirements: [],
  });
  expect(mocks.push).toHaveBeenCalledWith(`/t/${TENANT}/measures/${DOCUMENT}/${COMPONENT}`);
});

it("preserves selections across search, filters and revisions, edits guidance, and saves the document", async () => {
  const saved = { ...created, components: [{ ...created.components[0], description: "Updated reusable guidance", requirements: [
    { catalog_id: CATALOG, revision_id: REVISION, control_id: "ac-1", description: "Require MFA." },
    { catalog_id: CATALOG, revision_id: SECOND_REVISION, control_id: "ac-2", description: "Review accounts." },
  ] }, created.components[1]] };
  mocks.bffWrite.mockResolvedValue(saved);
  const user = userEvent.setup();
  render(<MeasureDetailWorkspace tenantId={TENANT} initialDocument={created} componentId={COMPONENT}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  await user.clear(screen.getByLabelText("Reusable description"));
  await user.type(screen.getByLabelText("Reusable description"), "Updated reusable guidance");
  await user.click(screen.getByRole("tab", { name: /Requirements/ }));
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add requirements" }));
  await screen.findByRole("option", { name: "Revision 1 · Published" });
  await user.selectOptions(screen.getByLabelText("Catalog revision"), REVISION);
  const first = await screen.findByRole("checkbox", { name: /ac-1 Access Policy/ });
  const controlRow = first.closest("li");
  expect(controlRow).not.toBeNull();
  await user.click(controlRow!.querySelector("summary")!);
  expect((await screen.findAllByText(/Review every/)).length).toBeGreaterThan(0);
  await user.click(first);
  await user.type(screen.getByLabelText("Search security controls"), "accounts");
  expect(screen.queryByRole("checkbox", { name: /ac-1 Access Policy/ })).not.toBeInTheDocument();
  await user.click(screen.getByText("Catalog filters"));
  await user.selectOptions(screen.getByLabelText("Security level"), "low");
  expect(screen.getByText("All selected requirements (1)")).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Catalog revision"), SECOND_REVISION);
  await user.click(await screen.findByRole("checkbox", { name: /ac-2 Account Management/ }));
  expect(screen.getByText("All selected requirements (2)")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add selected (2)" }));
  await user.click(await screen.findByText((_, element) => element?.tagName === "SUMMARY" && element.textContent?.includes("ac-1 · Access Policy") === true));
  await user.type(screen.getByLabelText("Implementation guidance for ac-1"), "Require MFA.");
  await user.click(await screen.findByText((_, element) => element?.tagName === "SUMMARY" && element.textContent?.includes("ac-2 · Account Management") === true));
  await user.type(screen.getByLabelText("Implementation guidance for ac-2"), "Review accounts.");
  await user.click(screen.getAllByText(/Related control mappings/)[0]);
  expect(await screen.findByText(/Advisory mapping/)).toBeInTheDocument();
  expect(screen.getByText(/Target set: Security · revision 2 · ac-2/)).toBeInTheDocument();
  await user.click(screen.getByRole("tab", { name: "Overview" }));
  expect(screen.getByLabelText("Reusable description")).toHaveValue("Updated reusable guidance");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(mocks.bffWrite).toHaveBeenCalledWith("PUT", `tenants/${TENANT}/component-definitions/${DOCUMENT}`, {
    title: "Security document", components: [
      { id: COMPONENT, type: "policy", title: "Multifactor authentication", description: "Updated reusable guidance", requirements: saved.components[0].requirements },
      { id: OTHER_COMPONENT, type: "software", title: "Audit logging", description: "Collect audit events.", requirements: [] },
    ],
  }));
  expect(await screen.findByRole("link", { name: "Export OSCAL JSON" })).toHaveAttribute("href", `/bff/tenants/${TENANT}/component-definitions/${DOCUMENT}/export`);
});

it("prevents duplicate associations and preserves existing guidance", async () => {
  const initial = { ...created, components: [{ ...created.components[0], requirements: [{
    catalog_id: CATALOG, revision_id: REVISION, control_id: "ac-1", description: "Existing guidance.",
  }] }, created.components[1]] };
  const user = userEvent.setup();
  render(<MeasureDetailWorkspace tenantId={TENANT} initialDocument={initial} componentId={COMPONENT}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  await user.click(screen.getByRole("tab", { name: /Requirements/ }));
  await user.click(screen.getByRole("button", { name: "Add requirements" }));
  await screen.findByRole("option", { name: "Revision 1 · Published" });
  await user.selectOptions(screen.getByLabelText("Catalog revision"), REVISION);
  expect(await screen.findByRole("checkbox", { name: /ac-1 Access Policy/ })).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: /ac-2 Account Management/ }));
  await user.click(screen.getByRole("button", { name: "Add selected (1)" }));
  await user.click(await screen.findByText((_, element) => element?.tagName === "SUMMARY" && element.textContent?.includes("ac-1 · Access Policy") === true));
  expect(screen.getByLabelText("Implementation guidance for ac-1")).toHaveValue("Existing guidance.");
});

it("keeps edits after save errors and warns before leaving", async () => {
  mocks.bffWrite.mockRejectedValue(new Error("Save failed; try again."));
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const user = userEvent.setup();
  render(<MeasureDetailWorkspace tenantId={TENANT} initialDocument={created} componentId={COMPONENT}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  await user.clear(screen.getByLabelText("Measure title"));
  await user.type(screen.getByLabelText("Measure title"), "Draft title");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Save failed; try again.");
  expect(screen.getByLabelText("Measure title")).toHaveValue("Draft title");
  await user.click(screen.getByRole("link", { name: "Our Measures & Controls" }));
  expect(confirm).toHaveBeenCalledWith("Discard unsaved measure changes?");
  expect(screen.getByLabelText("Measure title")).toHaveValue("Draft title");
  confirm.mockRestore();
});

it("confirms document deletion and warns that all components will be deleted", async () => {
  mocks.bffWrite.mockResolvedValue(undefined);
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const user = userEvent.setup();
  render(<MeasureDetailWorkspace tenantId={TENANT} initialDocument={created} componentId={COMPONENT}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  await user.click(screen.getByRole("tab", { name: "OSCAL Details" }));
  await user.click(screen.getByRole("button", { name: "Delete document" }));
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining("all 2 components"));
  await waitFor(() => expect(mocks.bffWrite).toHaveBeenCalledWith("DELETE", `tenants/${TENANT}/component-definitions/${DOCUMENT}`, {}));
  expect(mocks.push).toHaveBeenCalledWith(`/t/${TENANT}/measures`);
  confirm.mockRestore();
});

it("adds a component without replacing other components in the document", async () => {
  const third = { ...created.components[0], id: "55555555-5555-4555-8555-555555555557",
    oscal_uuid: "77777777-7777-4777-8777-777777777779", title: "Third measure", description: "Third guidance" };
  mocks.bffWrite.mockResolvedValue({ ...created, components: [...created.components, third] });
  const user = userEvent.setup();
  render(<MeasureDetailWorkspace tenantId={TENANT} initialDocument={created} componentId={COMPONENT}
    catalogs={[selectedCatalog]} catalogTotal={1} canWrite />);
  await user.click(screen.getByRole("tab", { name: "OSCAL Details" }));
  await user.click(screen.getByRole("button", { name: "Add component to this document" }));
  await user.type(screen.getByLabelText("Measure title"), "Third measure");
  await user.type(screen.getByLabelText("Reusable description"), "Third guidance");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(mocks.bffWrite).toHaveBeenCalledWith("PUT", `tenants/${TENANT}/component-definitions/${DOCUMENT}`, {
    title: "Security document", components: [
      { id: COMPONENT, type: "policy", title: "Multifactor authentication", description: "Protect privileged access.", requirements: [] },
      { id: OTHER_COMPONENT, type: "software", title: "Audit logging", description: "Collect audit events.", requirements: [] },
      { type: "policy", title: "Third measure", description: "Third guidance", requirements: [] },
    ],
  }));
  expect(screen.getByRole("heading", { name: "Third measure" })).toBeInTheDocument();
});
