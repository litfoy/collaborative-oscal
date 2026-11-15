import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemWorkspace } from "@/components/SystemWorkspace";
import { SystemsList } from "@/components/SystemsList";
import { SystemSecurityPlanWorkspace } from "@/components/SystemSecurityPlanWorkspace";
import type { ComponentDefinition, Implementation, InformationSystem, SystemComponent, SystemSecurityPlan, SystemSecurityPlanVersion } from "@/lib/types";

import { CATALOG, REVISION, TENANT, catalog, jsonResponse, page, revision } from "./fixtures";

const system: InformationSystem = {
  id: "system", tenant_id: TENANT, organization_id: null, name: "Identity", description: null,
  system_boundary: null, system_ids: [{ id: "old", "identifier-type": "scheme" }],
  information_types: [{ uuid: "info-uuid", title: "Identity data", description: "Original" }],
  operational_status: null, status_remarks: null, security_sensitivity_level: null, created_at: "", updated_at: "",
};
const component: SystemComponent = {
  id: "component", system_id: system.id, oscal_component_uuid: "component-uuid", is_system_component: false,
  source_snapshot_id: "snapshot", source_component_uuid: "source-uuid",
  component: { uuid: "component-uuid", type: "service", title: "Deployed service", description: "Deployed here", status: { state: "operational" } },
};
const definition: ComponentDefinition = {
  id: "definition", tenant_id: TENANT, title: "Guidance", oscal_document_uuid: "doc", oscal_version: "1.2.3",
  version: "1", components: [{ id: "source", oscal_uuid: "source-uuid", type: "service", title: "Reusable service", description: "Generic guidance", requirements: [] }],
  created_by: "", updated_by: "", created_at: "", updated_at: "",
};
const plan: SystemSecurityPlan = {
  id: "plan", tenant_id: TENANT, system_id: system.id, catalog_id: CATALOG, revision_id: REVISION,
  catalog_name: "Baseline", title: "Identity SSP", control_implementation_description: null,
  included_implementations: [{ implementation_id: "implementation", oscal_control_id: "ac-1", system_component_id: component.id }],
  baseline_control_count: 2, documented_control_count: 1, created_at: "", updated_at: "",
};
const implementation: Implementation = {
  id: "implementation", tenant_id: TENANT, organization_id: null, profile_id: null, catalog_id: CATALOG,
  revision_id: REVISION, oscal_control_id: "ac-1", description: "Contribution", status: "implemented",
  oscal_implementation_status: "implemented", system_id: system.id, system_component_id: null,
  responsibilities: [], evidence_references: [], created_by: "", updated_by: "", created_at: "", updated_at: "",
};
const version: SystemSecurityPlanVersion = {
  id: "version-1", system_security_plan_id: plan.id, catalog_id: CATALOG, revision_id: REVISION,
  oscal_document_uuid: "uuid", oscal_version: "1.2.3", document_version: "1.0", last_modified: "2025-01-01T00:00:00Z",
  content_sha256: "hash", diagnostics: [], created_at: "2025-01-01T00:00:00Z", created: true,
};
const validation = { valid: true, diagnostics: [], baseline_control_count: 2, documented_control_count: 1 };

function renderSystem() {
  return render(<SystemWorkspace tenantId={TENANT} initialSystem={system} initialComponents={[component]}
    initialPlans={[plan]} initialVersions={{ [plan.id]: [version] }} catalogs={[catalog()]}
    planRevisions={{ [plan.id]: revision() }}
    revisions={[{ catalog: catalog(), revision: revision() }]} definitions={[definition]} canWrite />);
}
function renderPlan() {
  return render(<SystemSecurityPlanWorkspace tenantId={TENANT} system={system} initialPlan={plan}
    components={[component]} initialImplementations={[implementation]} initialVersions={[version]}
    revision={revision()} initialRoot={page([])} canWrite />);
}

afterEach(() => vi.unstubAllGlobals());

describe("Systems workspaces", () => {
  it("searches systems and creates one without inventing system characteristics", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => jsonResponse({ ...system, id: "new", name: "New" }));
    vi.stubGlobal("fetch", fetchMock);
    render(<SystemsList tenantId={TENANT} initialSystems={[system]} initialCounts={{ system: { components: 1, plans: 1 } }} canWrite />);
    expect(screen.getByText(/1 components · 1 SSPs/)).toBeInTheDocument();
    await user.type(screen.getByRole("searchbox", { name: /search systems/i }), "absent");
    expect(screen.queryByRole("heading", { name: "Identity" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New system" }));
    await user.type(screen.getByLabelText("System name"), "New");
    await user.click(screen.getByRole("button", { name: "Create system" }));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toMatchObject({ name: "New", operational_status: null, system_ids: [], information_types: [] });
  });

  it("preserves structured rows and information type identity across edits and tabs", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => jsonResponse(system));
    vi.stubGlobal("fetch", fetchMock);
    renderSystem();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Changed | title");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Data | detail");
    await user.click(screen.getByRole("button", { name: "Components" }));
    await user.click(screen.getByRole("button", { name: "Overview" }));
    expect(screen.getByLabelText("Title")).toHaveValue("Changed | title");
    await user.click(screen.getByRole("button", { name: "Save System characteristics" }));
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.system_ids).toEqual([{ id: "old", identifier_type: "scheme" }]);
    expect(body.information_types).toEqual([{ uuid: "info-uuid", title: "Changed | title", description: "Data | detail" }]);
    expect(body.operational_status).toBeNull();
  });

  it("adopts a measure only with an explicit deployment description and status", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => jsonResponse(component));
    vi.stubGlobal("fetch", fetchMock);
    renderSystem();
    await user.click(screen.getByRole("button", { name: "Components" }));
    expect(screen.getByRole("link", { name: "View source snapshot" })).toHaveAttribute("href", `/bff/tenants/${TENANT}/component-definition-snapshots/snapshot/components/source-uuid/export`);
    await user.click(screen.getByRole("button", { name: "Adopt reusable measure" }));
    await user.selectOptions(screen.getByLabelText("Reusable Component Definition component"), "definition|source");
    expect(screen.getByLabelText("Actual deployment description")).toHaveValue("");
    expect(screen.getByLabelText("Component operational status")).toHaveValue("");
    await user.type(screen.getByLabelText("Actual deployment description"), "Deployed in production");
    await user.selectOptions(screen.getByLabelText("Component operational status"), "operational");
    await user.click(screen.getByRole("button", { name: "Adopt component" }));
    expect(fetchMock.mock.calls[0][0]).toContain("/components/adopt");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject({
      source_document_id: "definition", source_component_id: "source", description: "Deployed in production", status: "operational",
    });
  });

  it("edits a concrete component and creates an SSP pinned to the chosen revision", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (url: string, _init: RequestInit) =>
      jsonResponse(url.endsWith("/components/component") ? { ...component, component: { ...component.component, description: "Updated deployment" } } : plan));
    vi.stubGlobal("fetch", fetchMock);
    renderSystem();
    await user.click(screen.getByRole("button", { name: "Components" }));
    await user.click(screen.getByRole("button", { name: "Edit component" }));
    await user.clear(screen.getByLabelText("Actual deployment description"));
    await user.type(screen.getByLabelText("Actual deployment description"), "Updated deployment");
    await user.click(screen.getByRole("button", { name: "Save component" }));
    expect(await screen.findByText("Updated deployment")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Security plans" }));
    expect(screen.getByText(/1 immutable versions/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "New SSP" }));
    await user.selectOptions(screen.getByLabelText("Pinned Catalog revision"), `${CATALOG}|${REVISION}`);
    await user.type(screen.getByLabelText("SSP title"), "New plan");
    await user.click(screen.getByRole("button", { name: "Create SSP draft" }));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toMatchObject({ catalog_id: CATALOG, revision_id: REVISION, title: "New plan" });
  });

  it("finds documented and undocumented controls in the pinned baseline", async () => {
    const user = userEvent.setup();
    const controls = [
      { id: "c1", oscal_control_id: "ac-1", title: "Policy", group: null },
      { id: "c2", oscal_control_id: "ac-2", title: "Accounts", group: null },
    ];
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(page(controls))));
    renderPlan();
    await user.selectOptions(screen.getByLabelText("Documentation"), "undocumented");
    expect(await screen.findByRole("button", { name: /ac-2.*Accounts/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /ac-1.*Policy/ })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Documentation"), "documented");
    expect(screen.getByRole("button", { name: /ac-1.*Policy/ })).toBeVisible();
  });

  it("edits included contributions with the SSP's actual component and preserves unsaved plan changes", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (_url: string, _init: RequestInit) => jsonResponse({ ...implementation, description: "Edited" }));
    vi.stubGlobal("fetch", fetchMock);
    renderPlan();
    await user.click(screen.getByRole("button", { name: "Control implementation" }));
    await user.type(screen.getByLabelText("SSP document title"), " changed");
    await user.click(screen.getByRole("button", { name: "Edit contribution" }));
    expect(screen.getByLabelText("Actual system component")).toHaveValue("component");
    expect(screen.getByLabelText("Actual system component")).toBeDisabled();
    await user.clear(screen.getByLabelText("Requirement-specific implementation description"));
    await user.type(screen.getByLabelText("Requirement-specific implementation description"), "Edited");
    await user.click(screen.getByRole("button", { name: "Save requirement contribution changes" }));
    expect(await screen.findByText(/Requirement contribution: Edited/)).toBeInTheDocument();
    expect(screen.getByLabelText("SSP document title")).toHaveValue("Identity SSP changed");
    expect(fetchMock.mock.calls[0][0]).toContain("/implementations/implementation");
    await user.click(screen.getByRole("button", { name: "Versions" }));
    expect(screen.getByRole("button", { name: "Create immutable SSP version" })).toBeDisabled();
  });

  it("keeps an unfinished contribution draft across sections and blocks versioning until discarded", async () => {
    const user = userEvent.setup();
    renderPlan();
    await user.click(screen.getByRole("button", { name: "Control implementation" }));
    await user.click(screen.getByRole("button", { name: "Edit contribution" }));
    await user.type(screen.getByLabelText("Requirement-specific implementation description"), " draft");
    await user.click(screen.getByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: "Versions" }));
    expect(screen.getByRole("button", { name: "Create immutable SSP version" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Control implementation" }));
    await user.click(screen.getByRole("button", { name: "Resume contribution" }));
    expect(screen.getByLabelText("Requirement-specific implementation description")).toHaveValue("Contribution draft");
    await user.click(screen.getByRole("button", { name: "Discard draft" }));
    await user.click(screen.getByRole("button", { name: "Versions" }));
    expect(screen.getByRole("button", { name: "Create immutable SSP version" })).toBeEnabled();
  });

  it("shows failed validation diagnostics and prevents version creation", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ...validation, valid: false, diagnostics: [{ severity: "error", code: "system_ids_required", message: "Add an identifier." }] })));
    renderPlan();
    await user.click(screen.getByRole("button", { name: "Validation" }));
    await user.click(screen.getByRole("button", { name: "Validate working state" }));
    expect(await screen.findByText(/Add an identifier/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Versions" }));
    expect(screen.getByRole("button", { name: "Create immutable SSP version" })).toBeDisabled();
  });

  it("validates and creates a version while exports remain bound to each stored version", async () => {
    const user = userEvent.setup();
    const newVersion = { ...version, id: "version-2", document_version: "2.0" };
    const fetchMock = vi.fn(async (url: string) => jsonResponse(url.endsWith("/validation") ? validation : newVersion));
    vi.stubGlobal("fetch", fetchMock);
    renderPlan();
    await user.click(screen.getByRole("button", { name: "Validation" }));
    await user.click(screen.getByRole("button", { name: "Validate working state" }));
    expect(await screen.findByText("The current draft passes configured validation.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Versions" }));
    await user.click(screen.getByRole("button", { name: "Create immutable SSP version" }));
    const first = await screen.findByText("Version 2.0");
    expect(within(first.closest("li")!).getByRole("link", { name: "Export stored OSCAL JSON" })).toHaveAttribute("href", `/bff/tenants/${TENANT}/system-security-plans/plan/versions/version-2/export`);
    const old = screen.getByText("Version 1.0");
    expect(within(old.closest("li")!).getByRole("link", { name: "Export stored OSCAL JSON" })).toHaveAttribute("href", `/bff/tenants/${TENANT}/system-security-plans/plan/versions/version-1/export`);
    expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain(`/bff/tenants/${TENANT}/system-security-plans/plan/versions/version-1/export`);
  });
});
