// SPDX-License-Identifier: Apache-2.0
// Copyright The Collaborative OSCAL Authors.

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { ImplementationRegister } from "@/components/ImplementationRegister";
import type { Implementation, Profile } from "@/lib/types";
import { CATALOG, control, page, REVISION, TENANT } from "./fixtures";

const mocks = vi.hoisted(() => ({ bffGet: vi.fn(), bffWrite: vi.fn() }));
vi.mock("@/lib/bff-client", () => mocks);

const profile: Profile = {
  id: "profile", tenant_id: TENANT, catalog_id: CATALOG, revision_id: REVISION,
  title: "Baseline", control_ids: ["ac-1"], created_at: "2026-01-01", updated_at: "2026-01-01",
  concurrency_version: 1,
};
const saved: Implementation = {
  id: "implementation", tenant_id: TENANT, organization_id: null, profile_id: profile.id,
  catalog_id: CATALOG, revision_id: REVISION, oscal_control_id: "ac-1",
  description: "Policy implemented", status: "implemented",
  evidence_references: ["document:policy"], responsibilities: [
    { kind: "accountable", user_id: "person", role: "Owner" },
  ], created_by: "person", updated_by: "person", created_at: "2026-01-01", updated_at: "2026-01-02", concurrency_version: 1,
};

beforeEach(() => {
  mocks.bffGet.mockReset();
  mocks.bffWrite.mockReset();
  mocks.bffGet.mockImplementation(async (path: string) => {
    if (path.endsWith("implementation-options")) return {
      organizations: [{ id: "organization", name: "Operations" }],
      people: [{ id: "person", display_name: "Alex" }],
    };
    if (path.endsWith("/control") || path.includes("/controls/")) return control();
    return page([saved]);
  });
});

it("creates a revision-pinned implementation with scope, responsibility and evidence", async () => {
  const user = userEvent.setup();
  mocks.bffWrite.mockResolvedValue(saved);
  render(<ImplementationRegister tenantId={TENANT} profile={profile} canWrite initialControlId="ac-1" onBack={vi.fn()} />);
  expect(await screen.findByText("Normative requirement — read-only")).toBeInTheDocument();
  await screen.findByRole("option", { name: "Operations" });
  await user.selectOptions(screen.getByLabelText("Scope"), "organization");
  await user.type(screen.getByLabelText("Implementation description"), "Policy implemented");
  await user.selectOptions(screen.getByLabelText("Implementation status"), "implemented");
  await user.type(screen.getByLabelText(/Evidence references/), "document:policy");
  await user.click(screen.getByRole("button", { name: "Add responsibility" }));
  await user.selectOptions(screen.getByLabelText("Responsibility 1"), "accountable");
  await user.selectOptions(screen.getByLabelText("Person"), "person");
  await user.type(screen.getByLabelText("Role"), "Owner");
  await user.click(screen.getByRole("button", { name: "Save implementation" }));
  await waitFor(() => expect(mocks.bffWrite).toHaveBeenCalledWith(
    "POST", `tenants/${TENANT}/implementations`, {
      catalog_id: CATALOG, revision_id: REVISION, profile_id: profile.id,
      oscal_control_id: "ac-1", organization_id: "organization", description: "Policy implemented",
      status: "implemented", evidence_references: ["document:policy"],
      responsibilities: [{ kind: "accountable", user_id: "person", role: "Owner" }],
    },
  ));
  expect(screen.getByText(/Reported implementation is not an assessment/)).toBeInTheDocument();
});

it("opens a historical implementation using its own normative control endpoint", async () => {
  const user = userEvent.setup();
  render(<ImplementationRegister tenantId={TENANT} profile={{ ...profile, control_ids: ["ac-2"] }}
    canWrite={false} initialControlId={null} onBack={vi.fn()} />);
  await user.click(await screen.findByRole("button", { name: /ac-1 · implemented/ }));
  await screen.findByText("Normative requirement — read-only");
  await waitFor(() => expect(mocks.bffGet).toHaveBeenCalledWith(
    `tenants/${TENANT}/implementations/${saved.id}/control`, undefined, expect.any(AbortSignal),
  ));
  expect(screen.getByLabelText("Implementation description")).toBeDisabled();
  expect(screen.getByText(/Original revision:/)).toHaveTextContent(REVISION);
});

it("sends expected_version when updating an existing implementation", async () => {
  const user = userEvent.setup();
  const updated: Implementation = {
    ...saved,
    description: "Policy implemented (updated)",
    concurrency_version: saved.concurrency_version + 1,
  };
  mocks.bffWrite.mockResolvedValue(updated);
  render(<ImplementationRegister tenantId={TENANT} profile={profile} canWrite initialControlId={null} onBack={vi.fn()} />);
  await user.click(await screen.findByRole("button", { name: /ac-1 · implemented/ }));
  const description = screen.getByLabelText("Implementation description");
  await user.clear(description);
  await user.type(description, updated.description);
  await user.click(screen.getByRole("button", { name: "Save implementation" }));
  await waitFor(() =>
    expect(mocks.bffWrite).toHaveBeenCalledWith(
      "PUT",
      `tenants/${TENANT}/implementations/${saved.id}`,
      {
        expected_version: saved.concurrency_version,
        description: updated.description,
        status: saved.status,
        evidence_references: saved.evidence_references,
        responsibilities: saved.responsibilities,
      },
    ),
  );
});