import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileManager } from "@/components/ProfileManager";
import type { Profile, ProfileBrowserNode } from "@/lib/types";

import { CATALOG, REVISION, TENANT, catalog, control, revision } from "./fixtures";

const mocks = vi.hoisted(() => ({ bffGet: vi.fn(), bffWrite: vi.fn() }));
vi.mock("@/lib/bff-client", () => mocks);

const profile: Profile = {
  id: "profile-id", tenant_id: TENANT, catalog_id: CATALOG, revision_id: REVISION,
  title: "Access baseline", description: "Scope for the annual review", control_ids: ["ac-1"],
  created_at: "2026-11-10T00:00:00Z", updated_at: "2026-11-10T00:00:00Z",
};
const root = "/catalog/groups/0";
const parent = `${root}/controls/0`;
const child = `${parent}/controls/0`;
const nodes: ProfileBrowserNode[] = [
  { key: root, parent_key: null, kind: "group", id: "ac", title: "Access domain", text: "", properties: [] },
  { key: parent, parent_key: root, kind: "control", id: "ac-1", title: "Access policy", text: "Review policy annually.", properties: [{ name: "sec_level", value: "normal" }, { name: "modal_verb", value: "MUSS" }] },
  { key: child, parent_key: parent, kind: "control", id: "ac-1.1", title: "Policy exceptions", text: "Record exceptional approvals.", properties: [{ name: "sec_level", value: "high" }, { name: "modal_verb", value: "SOLLTE" }, { name: "audience", ns: "https://example.com/ns", value: "Auditors" }] },
  { key: "/catalog/controls/0", parent_key: null, kind: "control", id: "ir-1", title: "Response policy", text: "Handle incidents.", properties: [] },
];

function renderManager(profiles: Profile[] = [], canWrite = true) {
  return render(<ProfileManager tenantId={TENANT} profiles={profiles} catalogs={[catalog()]} canWrite={canWrite} />);
}
async function createWorkspace() {
  const user = userEvent.setup();
  renderManager();
  await user.click(screen.getByRole("button", { name: "Create profile" }));
  await screen.findByRole("region", { name: "Requirement browser" });
  return user;
}

beforeEach(() => {
  mocks.bffGet.mockReset();
  mocks.bffWrite.mockReset();
  mocks.bffGet.mockImplementation(async (path: string) => {
    if (path.endsWith("profile-browser")) return { nodes };
    if (path.includes("/controls/")) return control({ raw_control: { id: "ac-1", parts: [{ prose: "{{ insert: param, frequency }}" }] } });
    return { ...revision(), group_count: 1, source_document: {} };
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => vi.restoreAllMocks());

describe("Profile Builder", () => {
  it("uses a structured overview instead of editable ID forms", () => {
    renderManager([profile]);
    expect(screen.getByText("Access baseline")).toBeInTheDocument();
    expect(screen.getByText(profile.description!)).toBeInTheDocument();
    expect(screen.getByText(/1 selected requirements/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit profile" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Duplicate" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export OSCAL JSON" })).toHaveAttribute("href", `/bff/tenants/${TENANT}/profiles/${profile.id}/export`);
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("navigates groups and nested controls using expandable keyboard-accessible buttons", async () => {
    const user = await createWorkspace();
    const navigation = screen.getByRole("complementary", { name: "Catalog navigation" });
    expect(within(navigation).queryByRole("button", { name: /ac-1 Access policy/ })).not.toBeInTheDocument();
    const expand = within(navigation).getByRole("button", { name: "Expand ac" });
    expand.focus();
    await user.keyboard("{Enter}");
    expect(expand).toHaveAttribute("aria-expanded", "true");
    await user.click(within(navigation).getByRole("button", { name: "Expand ac-1" }));
    await user.click(within(navigation).getByRole("button", { name: "ac-1.1 Policy exceptions" }));
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).not.toBeChecked();
    await user.click(within(navigation).getByRole("button", { name: "Collapse ac" }));
    expect(within(navigation).queryByRole("button", { name: "ac-1.1 Policy exceptions" })).not.toBeInTheDocument();
  });

  it("searches prose and filters actual properties without losing selections", async () => {
    const user = await createWorkspace();
    await user.click(screen.getByRole("checkbox", { name: "ac-1 Access policy" }));
    await user.type(screen.getByRole("searchbox", { name: "Search requirements" }), "exceptional approvals");
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).not.toBeChecked();
    await user.selectOptions(screen.getByRole("combobox", { name: /Classification/ }), "MUSS");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/No requirements match/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(screen.getByRole("checkbox", { name: "ac-1 Access policy" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).not.toBeChecked();
    await user.selectOptions(screen.getByRole("combobox", { name: "Security level" }), "high");
    await user.click(screen.getByRole("button", { name: "Select all 1 matches" }));
    expect(screen.getByRole("tab", { name: "Selected Requirements (2)" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Deselect matches" }));
    expect(screen.getByRole("tab", { name: "Selected Requirements (1)" })).toBeInTheDocument();
    await user.click(screen.getByText("Advanced filters (0 active)"));
    await user.selectOptions(screen.getByRole("combobox", { name: "audience" }), "Auditors");
    expect(screen.getByText("audience: Auditors")).toBeInTheDocument();
    expect(screen.getByText("Advanced filters (1 active)")).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(screen.getByRole("checkbox", { name: "ac-1 Access policy" })).toBeChecked();
  });

  it("includes descendants only explicitly and saves a unique, revision-pinned selection", async () => {
    const user = await createWorkspace();
    await user.click(screen.getByRole("tab", { name: "Profile Settings" }));
    await user.type(screen.getByRole("textbox", { name: "Profile title" }), "Annual scope");
    await user.type(screen.getByRole("textbox", { name: "Description or purpose" }), "Annual audit");
    await user.click(screen.getByRole("tab", { name: "Catalog Browser" }));
    await user.click(screen.getByRole("checkbox", { name: "ac-1 Access policy" }));
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Select ac-1 and all descendants" }));
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).toBeChecked();
    mocks.bffWrite.mockResolvedValue({ ...profile, title: "Annual scope", description: "Annual audit", control_ids: ["ac-1", "ac-1.1"] });
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    await screen.findByText("Profile “Annual scope” saved.");
    expect(mocks.bffWrite).toHaveBeenCalledWith("POST", `tenants/${TENANT}/profiles`, {
      title: "Annual scope", description: "Annual audit", control_ids: ["ac-1", "ac-1.1"],
      catalog_id: CATALOG, revision_id: REVISION,
    });
    expect(screen.getByRole("link", { name: "Export OSCAL JSON" })).toHaveAttribute("href", `/bff/tenants/${TENANT}/profiles/${profile.id}/export`);
    await user.click(screen.getByRole("button", { name: "Back to profiles" }));
    await user.click(screen.getByRole("button", { name: "Edit profile" }));
    expect(await screen.findByRole("checkbox", { name: "ac-1 Access policy" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).toBeChecked();
  });

  it("edits and duplicates the original revision even when a newer catalog revision exists", async () => {
    const user = userEvent.setup();
    render(<ProfileManager tenantId={TENANT} profiles={[profile]} catalogs={[catalog({ latest_revision: revision({ id: "newer-revision" }) })]} canWrite />);
    await user.click(screen.getByRole("button", { name: "Duplicate" }));
    await screen.findByRole("region", { name: "Requirement browser" });
    expect(mocks.bffGet).toHaveBeenCalledWith(expect.stringContaining(`/revisions/${REVISION}/profile-browser`), undefined, expect.any(AbortSignal));
    expect(mocks.bffGet).not.toHaveBeenCalledWith(expect.stringContaining("newer-revision"), undefined, expect.anything());
    mocks.bffWrite.mockResolvedValue({ ...profile, id: "copy", title: "Access baseline (copy)" });
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(mocks.bffWrite).toHaveBeenCalledWith("POST", expect.any(String), expect.objectContaining({ revision_id: REVISION, control_ids: ["ac-1"] }));
    await screen.findByText("Profile “Access baseline (copy)” saved.");
    await user.click(screen.getByRole("button", { name: "Back to profiles" }));
    await user.click(screen.getAllByRole("button", { name: "Edit profile" })[1]);
    await screen.findByRole("region", { name: "Requirement browser" });
    mocks.bffWrite.mockResolvedValue({ ...profile, control_ids: ["ac-1", "ir-1"] });
    await user.click(screen.getByRole("checkbox", { name: "ir-1 Response policy" }));
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(mocks.bffWrite).toHaveBeenLastCalledWith("PUT", `tenants/${TENANT}/profiles/${profile.id}`, expect.objectContaining({ control_ids: ["ac-1", "ir-1"] }));
    await screen.findByText("Profile “Access baseline” saved.");
  });

  it("preserves selections across keyboard workspace navigation and reviews their original hierarchy", async () => {
    const user = await createWorkspace();
    await user.click(screen.getByRole("checkbox", { name: "ac-1 Access policy" }));
    await user.click(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" }));
    screen.getByRole("tab", { name: "Catalog Browser" }).focus();
    await user.keyboard("{ArrowRight}");
    const selection = screen.getByRole("tabpanel", { name: "Selected Requirements (2)" });
    expect(screen.getByRole("tab", { name: "Selected Requirements (2)" })).toHaveFocus();
    expect(within(selection).getByRole("heading", { name: "ac · Access domain" })).toBeInTheDocument();
    expect(within(selection).getByRole("heading", { name: "ac · Access domain › ac-1 · Access policy" })).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: "Search selected requirements" }), "exceptional");
    expect(within(selection).queryByRole("button", { name: "Remove ac-1" })).not.toBeInTheDocument();
    await user.click(within(selection).getByRole("button", { name: "ac-1.1 Policy exceptions" }));
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).toBeChecked();
    expect(screen.getByRole("complementary", { name: "Requirement details" })).toHaveFocus();
    await user.click(screen.getByRole("tab", { name: "Selected Requirements (2)" }));
    await user.click(screen.getByRole("button", { name: "Remove ac-1.1" }));
    await user.click(screen.getByRole("button", { name: "Clear selection search" }));
    expect(screen.getByRole("heading", { name: "Selected requirements (1)" })).toBeInTheDocument();
    expect(within(selection).getByRole("button", { name: "ac-1 Access policy" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Catalog Browser" }));
    await user.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(screen.getByRole("checkbox", { name: "ac-1 Access policy" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "ac-1.1 Policy exceptions" })).not.toBeChecked();
    screen.getByRole("tab", { name: "Catalog Browser" }).focus();
    await user.keyboard("{End}{Home}");
    expect(screen.getByRole("tab", { name: "Catalog Browser" })).toHaveFocus();
  });

  it("shows full requirement details and original OSCAL insertion text", async () => {
    const user = await createWorkspace();
    await user.click(screen.getByRole("button", { name: "Details for ac-1" }));
    const statement = await screen.findByRole("region", { name: "Requirement statement" });
    expect(within(statement).getByText("Review every [frequency].")).toBeVisible();
    expect(within(statement).getByText("Nested item")).toBeVisible();
    expect(screen.getByText("Catalog ID")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Hide details" }));
    expect(screen.queryByRole("complementary", { name: "Requirement details" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show details" }));
    expect(within(statement).getByText("Nested item")).toBeVisible();
    await user.click(screen.getByText("Technical OSCAL details"));
    await user.click(screen.getByText("Advanced technical view: source OSCAL JSON"));
    expect(screen.getByText(/insert: param, frequency/)).toBeVisible();
  });

  it("protects unsaved changes and retains the draft on save failure", async () => {
    const user = await createWorkspace();
    await user.click(screen.getByRole("tab", { name: "Profile Settings" }));
    await user.type(screen.getByRole("textbox", { name: "Profile title" }), "Draft");
    await user.click(screen.getByRole("tab", { name: "Catalog Browser" }));
    await user.click(screen.getByRole("checkbox", { name: "ac-1 Access policy" }));
    vi.mocked(window.confirm).mockReturnValue(false);
    await user.click(screen.getByRole("button", { name: "Back to profiles" }));
    expect(window.confirm).toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Draft" })).toBeInTheDocument();
    const unload = new Event("beforeunload", { cancelable: true });
    fireEvent(window, unload);
    expect(unload.defaultPrevented).toBe(true);
    let rejectSave: (cause: Error) => void = () => { throw new Error("Save has not started"); };
    mocks.bffWrite.mockImplementation(() => new Promise<Profile>((_resolve, reject) => { rejectSave = reject; }));
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByText("Saving…", { selector: "[role=status]" })).toBeInTheDocument();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    await act(async () => rejectSave(new Error("network")));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Save failed")).toBeInTheDocument();
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "ac-1 Access policy" })).toBeChecked();
    expect(screen.queryByRole("link", { name: "Export OSCAL JSON" })).not.toBeInTheDocument();
  });

  it("shows catalog loading errors and can retry", async () => {
    mocks.bffGet.mockRejectedValueOnce(new Error("offline"));
    const user = userEvent.setup();
    renderManager();
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    await user.click(await screen.findByRole("button", { name: "Retry catalog loading" }));
    expect(await screen.findByRole("checkbox", { name: "ac-1 Access policy" })).toBeInTheDocument();
  });

  it("does not allow read-only users to change selections", async () => {
    const user = userEvent.setup();
    renderManager([profile], false);
    await user.click(screen.getByRole("button", { name: "View profile" }));
    expect(await screen.findByRole("checkbox", { name: "ac-1 Access policy" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save profile" })).not.toBeInTheDocument();
  });

  it("paginates large requirement lists and preserves selections across pages", async () => {
    const largeNodes = Array.from({ length: 2050 }, (_, i) => ({
      ...nodes[1], key: `/catalog/controls/${i}`, parent_key: null, id: `c-${i}`, title: `Requirement ${i}`,
    }));
    mocks.bffGet.mockImplementation(async (path: string) => path.endsWith("profile-browser") ? { nodes: largeNodes } : revision());
    const user = await createWorkspace();
    expect(screen.getAllByRole("checkbox")).toHaveLength(50);
    await user.click(screen.getByRole("checkbox", { name: "c-0 Requirement 0" }));
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.queryByRole("checkbox", { name: "c-0 Requirement 0" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(screen.getByRole("checkbox", { name: "c-0 Requirement 0" })).toBeChecked();
    await waitFor(() => expect(screen.getByText("Page 1 of 41")).toBeInTheDocument());
  });

  it.each([10_000, 10_001])("enforces the explicit selection limit for %i matches without partial selection", async (count) => {
    const largeNodes = Array.from({ length: count }, (_, i) => ({
      ...nodes[1], key: `/catalog/controls/${i}`, parent_key: null, id: `c-${i}`, title: `Requirement ${i}`,
    }));
    mocks.bffGet.mockImplementation(async (path: string) => path.endsWith("profile-browser") ? { nodes: largeNodes } : revision());
    const user = await createWorkspace();
    const navigation = screen.getByRole("complementary", { name: "Catalog navigation" });
    expect(within(navigation).getAllByRole("button")).toHaveLength(102); // 100 nodes, all requirements, load more
    await user.click(screen.getByRole("button", { name: `Select all ${count} matches` }));
    if (count === 10_001) {
      expect(screen.getByRole("alert")).toHaveTextContent(/up to 10,000/);
      expect(screen.getByRole("tab", { name: "Selected Requirements (0)" })).toBeInTheDocument();
    } else {
      expect(screen.getByRole("tab", { name: "Selected Requirements (10000)" })).toBeInTheDocument();
      expect(screen.getAllByRole("checkbox")).toHaveLength(50);
      expect(screen.queryByRole("button", { name: "Remove c-0" })).not.toBeInTheDocument();
      await user.click(screen.getByRole("tab", { name: "Selected Requirements (10000)" }));
      expect(screen.getByText("10000 matching selected requirements · 10000 total selected")).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: /^Remove c-/ })).toHaveLength(50);
      await user.click(screen.getByRole("button", { name: "Next selected" }));
      expect(screen.getByRole("button", { name: "Remove c-50" })).toBeInTheDocument();
      await user.type(screen.getByRole("searchbox", { name: "Search selected requirements" }), "Requirement 9999");
      expect(screen.getByRole("button", { name: "Remove c-9999" })).toBeInTheDocument();
      expect(screen.getAllByRole("button", { name: /^Remove c-/ })).toHaveLength(1);
    }
  });
});
