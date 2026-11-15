import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { ComponentDefinitionWorkspace } from "@/components/ComponentDefinitionWorkspace";
import type { ComponentDefinition } from "@/lib/types";
import { catalog, page, revision, TENANT } from "./fixtures";

const mocks = vi.hoisted(() => ({ bffGet: vi.fn(), bffWrite: vi.fn() }));
vi.mock("@/lib/bff-client", () => mocks);

const CATALOG = "22222222-2222-4222-8222-222222222222";
const REVISION = "33333333-3333-4333-8333-333333333333";
const DOCUMENT = "44444444-4444-4444-8444-444444444444";
const COMPONENT = "55555555-5555-4555-8555-555555555555";

const created: ComponentDefinition = {
  id: DOCUMENT,
  tenant_id: TENANT,
  title: "Multifactor authentication",
  oscal_document_uuid: "66666666-6666-4666-8666-666666666666",
  oscal_version: "1.2.3",
  version: "1.0.0",
  components: [{
    id: COMPONENT,
    oscal_uuid: "77777777-7777-4777-8777-777777777777",
    type: "policy",
    title: "Multifactor authentication",
    description: "Require multifactor authentication for privileged access.",
    requirements: [],
  }],
  created_by: "88888888-8888-4888-8888-888888888888",
  updated_by: "88888888-8888-4888-8888-888888888888",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

it("requires explicit control selection and keeps mapped controls advisory", async () => {
  const saved = {
    ...created,
    components: [{
      ...created.components[0],
      requirements: [{
        catalog_id: CATALOG,
        revision_id: REVISION,
        control_id: "ac-1",
        description: "Require MFA for privileged accounts.",
      }],
    }],
  };
  mocks.bffGet.mockImplementation(async (path: string) => {
    if (path.endsWith("/revisions")) return page([revision({ id: REVISION, catalog_id: CATALOG })]);
    if (path.endsWith("/profile-browser")) return {
      nodes: [
        { key: "ac-1", parent_key: null, kind: "control", id: "ac-1", title: "Access Policy", text: "", properties: [] },
        { key: "ac-2", parent_key: null, kind: "control", id: "ac-2", title: "Account Management", text: "", properties: [] },
      ],
    };
    if (path.endsWith("/related-mappings")) return {
      items: [{
        collection_id: "99999999-9999-4999-8999-999999999999",
        collection_title: "Advisory mapping",
        mapping_uuid: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        entry_uuid: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        relationship: "equivalent-to",
        matching_rationale: "semantic",
        matched_side: "source",
        sources: [{ catalog_id: CATALOG, catalog_name: "Security", revision_id: REVISION, revision_number: 1, control_id: "ac-1", title: "Access Policy" }],
        targets: [{ catalog_id: CATALOG, catalog_name: "Security", revision_id: REVISION, revision_number: 1, control_id: "ac-2", title: "Account Management" }],
      }],
    };
    return page([]);
  });
  mocks.bffWrite.mockImplementation(async (method: string) => method === "POST" ? created : saved);

  const user = userEvent.setup();
  render(
    <ComponentDefinitionWorkspace
      tenantId={TENANT}
      initialDefinitions={[]}
      catalogs={[catalog({ id: CATALOG, name: "Security", latest_revision: revision({ id: REVISION, catalog_id: CATALOG }) })]}
      catalogTotal={1}
      canWrite
    />,
  );

  await user.type(screen.getAllByLabelText("Measure title")[0], "Multifactor authentication");
  await user.click(screen.getByRole("button", { name: "Create measure" }));
  const selectedControl = await screen.findByRole("checkbox", { name: /ac-1 Access Policy/ });
  expect(selectedControl).not.toBeChecked();
  await user.click(selectedControl);
  await user.type(
    screen.getByLabelText("How this measure addresses ac-1"),
    "Require MFA for privileged accounts.",
  );
  await user.click(await screen.findByText(/Related controls in existing mappings/));
  await screen.findByText("Advisory mapping");
  expect(screen.getByRole("checkbox", { name: /ac-2 Account Management/ })).not.toBeChecked();
  expect(screen.queryByLabelText("How this measure addresses ac-2")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(mocks.bffWrite).toHaveBeenLastCalledWith(
    "PUT",
    `tenants/${TENANT}/component-definitions/${DOCUMENT}`,
    {
      title: "Multifactor authentication",
      components: [{
        id: COMPONENT,
        type: "policy",
        title: "Multifactor authentication",
        description: "Require multifactor authentication for privileged access.",
        requirements: [{
          catalog_id: CATALOG,
          revision_id: REVISION,
          control_id: "ac-1",
          description: "Require MFA for privileged accounts.",
        }],
      }],
    },
  ));
});
