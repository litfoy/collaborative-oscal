// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { ComplianceExplorerRequirementsView } from "@/components/ComplianceExplorerRequirementsView";
import { ApiError } from "@/lib/errors";
import { LocaleProvider } from "@/lib/i18n/provider";
import type { ComplianceExplorerPage, InformationSystem, Profile } from "@/lib/types";

const mocks = vi.hoisted(() => ({ bffGet: vi.fn() }));
vi.mock("@/lib/bff-client", () => ({ bffGet: mocks.bffGet }));

const tenantId = "11111111-1111-4111-8111-111111111111";
const systemId = "22222222-2222-4222-8222-222222222222";
const secondSystemId = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const systems: InformationSystem[] = [
  {
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
  },
  {
    id: secondSystemId,
    tenant_id: tenantId,
    organization_id: null,
    name: "Analytics System",
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
  },
];

const profiles: Profile[] = [
  {
    id: "33333333-3333-4333-8333-333333333333",
    tenant_id: tenantId,
    catalog_id: "44444444-4444-4444-8444-444444444444",
    revision_id: "55555555-5555-4555-8555-555555555555",
    title: "Security baseline",
    control_ids: ["ac-1"],
    created_at: "",
    updated_at: "",
    concurrency_version: 1,
  },
  {
    id: "66666666-6666-4666-8666-666666666666",
    tenant_id: tenantId,
    catalog_id: "44444444-4444-4444-8444-444444444444",
    revision_id: "55555555-5555-4555-8555-555555555555",
    title: "Privacy baseline",
    control_ids: ["ac-2"],
    created_at: "",
    updated_at: "",
    concurrency_version: 1,
  },
];

const explorerPage: ComplianceExplorerPage = {
  system: { id: systemId, name: "Payments System" },
  profiles: profiles.map((profile) => ({ id: profile.id, title: profile.title })),
  total: 2,
  limit: 20,
  offset: 0,
  items: [
    {
      reference: {
        catalog_id: "44444444-4444-4444-8444-444444444444",
        revision_id: "55555555-5555-4555-8555-555555555555",
        oscal_control_id: "ac-1",
      },
      title: "Access policy",
      memberships: [
        {
          profile_id: profiles[0].id,
          profile_title: profiles[0].title,
          profile_import_id: "77777777-7777-4777-8777-777777777777",
        },
        {
          profile_id: profiles[1].id,
          profile_title: profiles[1].title,
          profile_import_id: "88888888-8888-4888-8888-888888888888",
        },
      ],
      implementations: [
        {
          id: "99999999-9999-4999-8999-999999999999",
          status: "implemented",
          oscal_implementation_status: "implemented",
          oscal_status_explanation: null,
          profile_id: profiles[0].id,
          profile_import_id: "77777777-7777-4777-8777-777777777777",
          system_component_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          system_component: {
            id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            title: "Gateway",
          },
        },
        {
          id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          status: "in_progress",
          oscal_implementation_status: "partial",
          oscal_status_explanation: null,
          profile_id: profiles[1].id,
          profile_import_id: "88888888-8888-4888-8888-888888888888",
          system_component_id: null,
          system_component: null,
        },
      ],
    },
    {
      reference: {
        catalog_id: "44444444-4444-4444-8444-444444444444",
        revision_id: "55555555-5555-4555-8555-555555555555",
        oscal_control_id: "ac-2",
      },
      title: "Account management",
      memberships: [
        {
          profile_id: profiles[0].id,
          profile_title: profiles[0].title,
          profile_import_id: "77777777-7777-4777-8777-777777777777",
        },
      ],
      implementations: [],
    },
  ],
};

beforeEach(() => {
  mocks.bffGet.mockReset();
});

it("applies system/profile selection and renders shared memberships with implementation details", async () => {
  const user = userEvent.setup();
  mocks.bffGet.mockResolvedValue(explorerPage);

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={profiles} />
    </LocaleProvider>,
  );

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByLabelText("Privacy baseline"));
  expect(screen.getByText("Selected Profiles: 2/5")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Apply selection" }));

  await waitFor(() =>
    expect(mocks.bffGet).toHaveBeenCalledWith(
      `tenants/${tenantId}/systems/${systemId}/compliance-explorer`,
      expect.objectContaining({
        profile_id: [profiles[0].id, profiles[1].id],
        limit: 20,
        offset: 0,
      }),
    ),
  );

  expect(await screen.findByRole("table", { name: "Compliance explorer requirements" })).toBeVisible();
  expect(screen.getByRole("status", { name: "Applied results context" })).toBeVisible();
  expect(screen.getByText("Applied Profile count")).toBeVisible();
  expect(screen.getByText("ac-1")).toBeVisible();
  const requirementsTable = screen.getByRole("table", { name: "Compliance explorer requirements" });
  expect(within(requirementsTable).getByText("Security baseline, Privacy baseline")).toBeVisible();
  expect(within(requirementsTable).getByText("Workflow statuses")).toBeVisible();
  expect(within(requirementsTable).getByText("OSCAL implementation statuses")).toBeVisible();
  expect(screen.getByText("No system implementation documented")).toBeVisible();

  await user.click(screen.getByRole("button", { name: "Toggle details for ac-1" }));
  expect(await screen.findByText("99999999-9999-4999-8999-999999999999")).toBeVisible();
  expect(screen.getByText("Gateway (aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa)")).toBeVisible();
  expect(screen.getByText("Not explicitly linked")).toBeVisible();
});

it("rejects invalid draft selection and enforces the 1 to 5 profile limit", async () => {
  const user = userEvent.setup();
  const manyProfiles: Profile[] = Array.from({ length: 6 }, (_entry, index) => ({
    id: `66666666-6666-4666-8666-66666666666${index}`,
    tenant_id: tenantId,
    catalog_id: "44444444-4444-4444-8444-444444444444",
    revision_id: "55555555-5555-4555-8555-555555555555",
    title: `Profile ${index + 1}`,
    control_ids: [`ac-${index + 1}`],
    created_at: "",
    updated_at: "",
    concurrency_version: 1,
  }));

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={manyProfiles} />
    </LocaleProvider>,
  );

  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Select one System and between 1 and 5 Profiles, then apply.");

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Select between 1 and 5 Profiles.");

  for (let index = 1; index <= 6; index += 1) {
    await user.click(screen.getByLabelText(`Profile ${index}`));
  }

  const selected = manyProfiles
    .map((profile) => screen.getByLabelText(profile.title) as HTMLInputElement)
    .filter((checkbox) => checkbox.checked);
  expect(selected).toHaveLength(5);
  expect(screen.getByText("Selected Profiles: 5/5")).toBeVisible();
});

it("supports server-side pagination and empty states", async () => {
  const user = userEvent.setup();
  mocks.bffGet
    .mockResolvedValueOnce({
      ...explorerPage,
      total: 21,
      items: [explorerPage.items[0]],
    })
    .mockResolvedValueOnce({
      ...explorerPage,
      total: 21,
      offset: 20,
      items: [explorerPage.items[1]],
    })
    .mockResolvedValueOnce({
      ...explorerPage,
      total: 0,
      items: [],
    });

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={profiles} />
    </LocaleProvider>,
  );

  expect(screen.getByText("Select one System and between 1 and 5 Profiles, then apply.")).toBeVisible();

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  await screen.findByRole("table", { name: "Compliance explorer requirements" });

  await user.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() =>
    expect(mocks.bffGet).toHaveBeenLastCalledWith(
      `tenants/${tenantId}/systems/${systemId}/compliance-explorer`,
      expect.objectContaining({ offset: 20 }),
    ),
  );

  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  expect(await screen.findByText("No selected Controls are available for the current selection.")).toBeVisible();
});

it("renders German labels and supports keyboard interaction", async () => {
  const user = userEvent.setup();
  mocks.bffGet.mockResolvedValue(explorerPage);

  render(
    <LocaleProvider locale="de">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={profiles} />
    </LocaleProvider>,
  );

  expect(screen.getByRole("heading", { name: "Konformitäts-Explorer" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Auswahl anwenden" })).toBeVisible();
  expect(screen.getByText("Ausgewählte Anforderungsprofile: 0/5")).toBeVisible();

  const profileBox = screen.getByLabelText("Security baseline");
  profileBox.focus();
  await user.keyboard(" ");
  expect(profileBox).toBeChecked();

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByRole("button", { name: "Auswahl anwenden" }));
  expect(await screen.findByRole("table", { name: "Anforderungsansicht im Konformitäts-Explorer" })).toBeVisible();
  expect(screen.getByText("Keine System-Umsetzung dokumentiert")).toBeVisible();
});

it("surfaces request errors", async () => {
  const user = userEvent.setup();
  mocks.bffGet.mockRejectedValue(new ApiError("forbidden", 403, "forbidden"));

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={profiles} />
    </LocaleProvider>,
  );

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByRole("button", { name: "Apply selection" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "You do not have access to this workspace.",
  );
});

it("keeps applied System context explicit after changing the draft System", async () => {
  const user = userEvent.setup();
  mocks.bffGet.mockResolvedValue(explorerPage);

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={profiles} />
    </LocaleProvider>,
  );

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  await screen.findByRole("table", { name: "Compliance explorer requirements" });

  await user.selectOptions(screen.getByLabelText("System"), secondSystemId);

  const appliedContext = screen.getByRole("status", { name: "Applied results context" });
  expect(within(appliedContext).getByText("Applied System")).toBeVisible();
  expect(within(appliedContext).getByText("Payments System")).toBeVisible();
  expect(screen.getByText(/The draft selection differs from the applied scope/)).toBeVisible();
  expect(screen.getByRole("table", { name: "Compliance explorer requirements" })).toBeVisible();
});

it("keeps applied Profile context explicit after changing the draft Profiles", async () => {
  const user = userEvent.setup();
  mocks.bffGet.mockResolvedValue({
    ...explorerPage,
    profiles: [{ id: profiles[0].id, title: profiles[0].title }],
  });

  render(
    <LocaleProvider locale="en">
      <ComplianceExplorerRequirementsView tenantId={tenantId} systems={systems} profiles={profiles} />
    </LocaleProvider>,
  );

  await user.selectOptions(screen.getByLabelText("System"), systemId);
  await user.click(screen.getByLabelText("Security baseline"));
  await user.click(screen.getByRole("button", { name: "Apply selection" }));
  await screen.findByRole("table", { name: "Compliance explorer requirements" });

  await user.click(screen.getByLabelText("Privacy baseline"));

  const appliedContext = screen.getByRole("status", { name: "Applied results context" });
  expect(within(appliedContext).getByText("Applied Profiles")).toBeVisible();
  expect(within(appliedContext).getByText("Security baseline")).toBeVisible();
  expect(screen.getByText(/The draft selection differs from the applied scope/)).toBeVisible();
  expect(screen.getByRole("table", { name: "Compliance explorer requirements" })).toBeVisible();
});

