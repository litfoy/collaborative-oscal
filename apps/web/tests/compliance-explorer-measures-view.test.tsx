// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ComplianceExplorerMeasuresView } from "@/components/ComplianceExplorerMeasuresView";
import { ComplianceExplorerRequirementsView } from "@/components/ComplianceExplorerRequirementsView";
import { LocaleProvider } from "@/lib/i18n/provider";
import type { ComplianceExplorerPage, InformationSystem, Profile } from "@/lib/types";

const mocks = vi.hoisted(() => ({ bffGet: vi.fn() }));
vi.mock("@/lib/bff-client", () => ({ bffGet: mocks.bffGet }));

const tenantId = "11111111-1111-4111-8111-111111111111";
const systemId = "22222222-2222-4222-8222-222222222222";
const revisionId = "55555555-5555-4555-8555-555555555555";
const catalogId = "44444444-4444-4444-8444-444444444444";

const systems: InformationSystem[] = [{
  id: systemId,
  tenant_id: tenantId,
  organization_id: null,
  name: "Payments System",
  description: null,
  system_boundary: null,
  system_ids: [],
  information_types: [],
  operational_status: null,
  status_remarks: null,
  security_sensitivity_level: null,
  created_at: "",
  updated_at: "",
  concurrency_version: 1,
}];

const profiles: Profile[] = [{
  id: "33333333-3333-4333-8333-333333333333",
  tenant_id: tenantId,
  catalog_id: catalogId,
  revision_id: revisionId,
  title: "Security baseline",
  control_ids: ["ac-1", "ac-2", "ac-3", "ac-4"],
  created_at: "",
  updated_at: "",
  concurrency_version: 1,
}];

function control(controlId: string, title: string, implementations: ComplianceExplorerPage["items"][number]["implementations"]): ComplianceExplorerPage["items"][number] {
  return {
    reference: { catalog_id: catalogId, revision_id: revisionId, oscal_control_id: controlId },
    title,
    memberships: [{
      profile_id: profiles[0].id,
      profile_title: profiles[0].title,
      profile_import_id: "77777777-7777-4777-8777-777777777777",
    }],
    implementations,
  };
}

const measuresPage: ComplianceExplorerPage = {
  system: { id: systemId, name: "Payments System" },
  profiles: [{ id: profiles[0].id, title: profiles[0].title }],
  total: 21,
  limit: 20,
  offset: 0,
  items: [
    control("ac-1", "Access policy", [
      {
        id: "impl-gateway-1",
        status: "implemented",
        oscal_implementation_status: "implemented",
        oscal_status_explanation: null,
        profile_id: profiles[0].id,
        profile_import_id: "77777777-7777-4777-8777-777777777777",
        system_component_id: "component-gateway",
        system_component: { id: "component-gateway", title: "Shared title" },
      },
    ]),
    control("ac-2", "Account management", [
      {
        id: "impl-gateway-2",
        status: "in_progress",
        oscal_implementation_status: "partial",
        oscal_status_explanation: null,
        profile_id: profiles[0].id,
        profile_import_id: "77777777-7777-4777-8777-777777777777",
        system_component_id: "component-gateway",
        system_component: { id: "component-gateway", title: "Shared title" },
      },
      {
        id: "impl-other",
        status: "not_started",
        oscal_implementation_status: null,
        oscal_status_explanation: null,
        profile_id: profiles[0].id,
        profile_import_id: "77777777-7777-4777-8777-777777777777",
        system_component_id: "component-other",
        system_component: { id: "component-other", title: "Shared title" },
      },
    ]),
    control("ac-3", "Incident response", [{
      id: "impl-unlinked",
      status: "implemented",
      oscal_implementation_status: "implemented",
      oscal_status_explanation: null,
      profile_id: profiles[0].id,
      profile_import_id: "77777777-7777-4777-8777-777777777777",
      system_component_id: null,
      system_component: null,
    }]),
    control("ac-4", "Audit review", []),
  ],
};

it("groups the current page by explicit component identity without merging identical titles", () => {
  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerMeasuresView page={measuresPage} />
    </LocaleProvider>,
  );

  expect(screen.getByText(/Measures grouping covers the current page only: 4 of 21/)).toBeVisible();
  expect(screen.getByRole("heading", { name: "Linked System Components" })).toBeVisible();
  expect(screen.getByText("2 Component groups on this page")).toBeVisible();

  const sharedTitleGroups = screen.getAllByRole("region", { name: "System Component: Shared title" });
  expect(sharedTitleGroups).toHaveLength(2);
  const gateway = sharedTitleGroups.find((region) => within(region).queryByText(/component-gateway/));
  const other = sharedTitleGroups.find((region) => within(region).queryByText(/component-other/));
  expect(gateway).toBeDefined();
  expect(other).toBeDefined();
  expect(within(gateway!).getByText(/ac-1/)).toBeVisible();
  expect(within(gateway!).getByText(/ac-2/)).toBeVisible();
  expect(within(gateway!).getByText(/impl-gateway-1/)).toBeVisible();
  expect(within(gateway!).getByText(/impl-gateway-2/)).toBeVisible();
  expect(within(other!).getByText(/ac-2/)).toBeVisible();
  expect(within(other!).getByText(/impl-other/)).toBeVisible();

  expect(screen.getByRole("region", { name: "Implementations without an assigned System Component" })).toBeVisible();
  expect(screen.getByText(/not explicitly linked to a reusable System Component/)).toBeVisible();
  expect(screen.getByText("impl-unlinked")).toBeVisible();
  expect(screen.getByRole("region", { name: "Selected Controls without documented system Implementations" })).toBeVisible();
  expect(screen.getByText(/have no documented implementation records on this page/)).toBeVisible();
  expect(screen.getByText("ac-4")).toBeVisible();
});

it("switches views without another API request and keeps shared pagination state", async () => {
  const user = userEvent.setup();
  mocks.bffGet
    .mockResolvedValueOnce(measuresPage)
    .mockResolvedValueOnce({
      ...measuresPage,
      offset: 20,
      items: [control("ac-5", "Second-page control", [])],
    });

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={[profiles[0]]} />
    </LocaleProvider>,
  );

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  await screen.findByRole("table", { name: "Compliance explorer requirements" });
  expect(screen.getByText("ac-1")).toBeVisible();

  expect(mocks.bffGet).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Measures" }));
  expect(mocks.bffGet).toHaveBeenCalledTimes(1);
  expect(screen.getByText("ac-1")).toBeVisible();
  expect(screen.getAllByText(new RegExp(`${catalogId} / ${revisionId}`)).length).toBeGreaterThan(0);
  const measuresButton = screen.getByRole("button", { name: "Measures" });
  expect(measuresButton).toHaveAttribute("aria-pressed", "true");

  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(mocks.bffGet).toHaveBeenCalledTimes(2);
  expect(await screen.findByText(/Measures grouping covers the current page only: 1 of 21/)).toBeVisible();
  expect(screen.queryByText("ac-1")).not.toBeInTheDocument();
});

it("renders German Measures labels and keeps applied/draft context visible", async () => {
  const user = userEvent.setup();
  mocks.bffGet.mockResolvedValue(measuresPage);

  render(
    <LocaleProvider locale="de">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={[profiles[0]]} />
    </LocaleProvider>,
  );

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByRole("button", { name: "Auswahl anwenden" }));
  await screen.findByRole("button", { name: "Maßnahmen" });
  await user.click(screen.getByRole("button", { name: "Maßnahmen" }));

  const measuresButton = screen.getByRole("button", { name: "Maßnahmen" });
  expect(measuresButton).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText(/Die Gruppierung der Maßnahmen betrifft nur die aktuelle Seite/)).toBeVisible();
  await user.click(screen.getByLabelText("Security baseline"));
  expect(screen.getByText(/Die Entwurfsauswahl unterscheidet sich vom angewendeten Umfang/)).toBeVisible();
});

it("preserves individual traceability for two Implementations sharing a Control and Component", () => {
  const tracePage: ComplianceExplorerPage = {
    ...measuresPage,
    total: 1,
    limit: 20,
    offset: 0,
    items: [control("ac-1", "Access policy", [
      {
        id: "impl-a",
        status: "in_progress",
        oscal_implementation_status: "partial",
        oscal_status_explanation: "Partial release in test",
        profile_id: "profile-a",
        profile_import_id: "import-a",
        system_component_id: "component-gateway",
        system_component: { id: "component-gateway", title: "Gateway" },
      },
      {
        id: "impl-b",
        status: "implemented",
        oscal_implementation_status: "implemented",
        oscal_status_explanation: null,
        profile_id: "profile-b",
        profile_import_id: "import-b",
        system_component_id: "component-gateway",
        system_component: { id: "component-gateway", title: "Gateway" },
      },
    ])],
  };

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerMeasuresView page={tracePage} />
    </LocaleProvider>,
  );

  const gateway = screen.getByRole("region", { name: "System Component: Gateway" });
  const association = within(gateway).getByText("ac-1").closest("li");
  expect(association).not.toBeNull();
  const scoped = within(association!);
  expect(scoped.getByText("impl-a")).toBeVisible();
  expect(scoped.getByText("In progress")).toBeVisible();
  expect(scoped.getByText("Partially implemented")).toBeVisible();
  expect(scoped.getByText("Partial release in test")).toBeVisible();
  expect(scoped.getByText("profile-a / import-a")).toBeVisible();
  expect(scoped.getByText(new RegExp(`${catalogId} / ${revisionId}`))).toBeVisible();

  const implB = scoped.getByText("impl-b").closest("li");
  expect(implB).not.toBeNull();
  const implBScoped = within(implB!);
  expect(implBScoped.getAllByText("Implemented")).toHaveLength(2);
  expect(implBScoped.getByText("profile-b / import-b")).toBeVisible();
});
